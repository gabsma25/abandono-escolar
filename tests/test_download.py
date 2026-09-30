"""Download, cópia local e orquestração da aquisição — com servidor falso.

Nenhuma requisição de rede: `ServidorFalso` imita requests.Session.get com
Range/If-Range, ETag e queda de conexão no meio da transferência.
"""
from __future__ import annotations

import os

import pytest
import requests

from src.aquisicao import (
    ClienteInep,
    Link,
    adquirir,
    baixar,
    copiar_local,
    verificar_manifesto,
)
from src.integridade import ErroIntegridade, Referencia
from tests.conftest import sha256

URL = "https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/X.zip"
CONTEUDO = bytes(range(256)) * 4096   # 1 MiB


class RespostaFalsa:
    def __init__(self, status: int, corpo: bytes, headers: dict, falha_apos: int | None = None):
        self.status_code, self._corpo, self.headers = status, corpo, headers
        self._falha_apos = falha_apos

    @property
    def text(self) -> str:
        return self._corpo.decode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            e = requests.HTTPError(f"HTTP {self.status_code}")
            e.response = self  # type: ignore[assignment]
            raise e

    def iter_content(self, tamanho: int):
        enviado = 0
        for i in range(0, len(self._corpo), 64 * 1024):
            if self._falha_apos is not None and enviado >= self._falha_apos:
                raise requests.ConnectionError("conexão caiu")
            bloco = self._corpo[i:i + 64 * 1024]
            enviado += len(bloco)
            yield bloco


class ServidorFalso:
    """{url: bytes}; `quedas` = quantas respostas cortam a conexão no meio."""

    def __init__(self, arquivos: dict[str, bytes], etag: str = '"v1"', quedas: int = 0):
        self.arquivos, self.etag, self.quedas = arquivos, etag, quedas
        self.pedidos: list[dict] = []

    def get(self, url, headers=None, stream=False, timeout=None):
        headers = headers or {}
        self.pedidos.append({"url": url, **headers})
        if url not in self.arquivos:
            return RespostaFalsa(404, b"", {})
        corpo = self.arquivos[url]
        falha = None
        if self.quedas:
            self.quedas -= 1
            falha = len(corpo) // 3
        rng = headers.get("Range")
        if rng and headers.get("If-Range") == self.etag:
            inicio = int(rng.removeprefix("bytes=").rstrip("-"))
            parte = corpo[inicio:]
            return RespostaFalsa(206, parte, {
                "Content-Range": f"bytes {inicio}-{len(corpo) - 1}/{len(corpo)}",
                "Content-Length": str(len(parte)), "ETag": self.etag}, falha)
        return RespostaFalsa(200, corpo, {"Content-Length": str(len(corpo)), "ETag": self.etag}, falha)


def _cliente(servidor: ServidorFalso) -> ClienteInep:
    return ClienteInep(servidor, pausa=0, espera_base=0)


def test_baixa_confere_e_promove(tmp_path):
    servidor = ServidorFalso({URL: CONTEUDO})
    destino = tmp_path / "origem" / "X.zip"
    assert baixar(_cliente(servidor), URL, destino, Referencia(sha256(CONTEUDO)),
                  tmp_path / "cache", progresso=False) == "baixado"
    assert destino.read_bytes() == CONTEUDO
    assert not list((tmp_path / "cache").iterdir())   # .parcial e .json removidos


def test_queda_no_meio_retoma_com_range(tmp_path):
    servidor = ServidorFalso({URL: CONTEUDO}, quedas=1)
    destino = tmp_path / "origem" / "X.zip"
    baixar(_cliente(servidor), URL, destino, Referencia(sha256(CONTEUDO)), tmp_path / "cache", progresso=False)
    assert destino.read_bytes() == CONTEUDO
    assert "Range" not in servidor.pedidos[0]
    assert servidor.pedidos[1]["Range"].startswith("bytes=") and servidor.pedidos[1]["Range"] != "bytes=0-"
    assert servidor.pedidos[1]["If-Range"] == '"v1"'


def test_arquivo_mudou_no_servidor_recomeca_do_zero(tmp_path):
    """If-Range com ETag antigo: o servidor manda 200 e nada é emendado."""
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "X.zip.parcial").write_bytes(b"pedaco da versao antiga")
    (cache / "X.zip.parcial.json").write_text('{"url": "u", "validador": "\\"v0\\""}', encoding="utf-8")
    servidor = ServidorFalso({URL: CONTEUDO}, etag='"v1"')
    destino = tmp_path / "origem" / "X.zip"
    baixar(_cliente(servidor), URL, destino, Referencia(sha256(CONTEUDO)), cache, progresso=False)
    assert destino.read_bytes() == CONTEUDO


def test_hash_divergente_nao_entra_em_origem(tmp_path, divergente_temporario):
    servidor = ServidorFalso({URL: b"versao revisada pelo INEP"})
    destino = tmp_path / "origem" / "X.zip"
    with pytest.raises(ErroIntegridade) as erro:
        baixar(_cliente(servidor), URL, destino, Referencia(sha256(CONTEUDO)), tmp_path / "cache",
               progresso=False)
    assert "X.zip" in str(erro.value) and sha256(CONTEUDO) in str(erro.value)
    assert not destino.exists()
    assert [p.read_bytes() for p in divergente_temporario.iterdir()] == [b"versao revisada pelo INEP"]


def test_copia_local_nao_altera_a_fonte(tmp_path):
    fonte = tmp_path / "Downloads" / "X.zip"
    fonte.parent.mkdir()
    fonte.write_bytes(CONTEUDO)
    os.utime(fonte, ns=(10**18, 10**18))
    destino = tmp_path / "origem" / "X.zip"
    copiar_local(fonte, destino, Referencia(sha256(CONTEUDO)), tmp_path / "cache")
    assert destino.read_bytes() == CONTEUDO
    assert fonte.read_bytes() == CONTEUDO and fonte.stat().st_mtime_ns == 10**18


# ── adquirir: manifesto como especificação ─────────────────────────────────

def _manifesto(tmp_path, linhas: list[tuple[str, str, bytes]]) -> tuple:
    raiz = tmp_path / "dados"
    m = tmp_path / "MANIFEST.csv"
    texto = "estagio,origem,ano,tabela,arquivo,sha256,data_download\n"
    for estagio, arquivo, conteudo in linhas:
        texto += f"{estagio},inep,2023,indicador_ATU_escolas,{arquivo},{sha256(conteudo)},2026-09-15\n"
    m.write_text(texto, encoding="utf-8")
    return m, raiz


def test_adquirir_copia_do_local_e_segunda_vez_nao_faz_nada(tmp_path):
    m, raiz = _manifesto(tmp_path, [("origem", "origem/indicadores/X.zip", CONTEUDO)])
    local = tmp_path / "Downloads"
    local.mkdir()
    (local / "X.zip").write_bytes(CONTEUDO)
    (local / "FORA_DO_MANIFESTO.zip").write_bytes(b"nao copiar")
    kw = {"manifesto": m, "raiz": raiz, "cache": tmp_path / "cache"}

    r1 = adquirir([local], **kw)
    r2 = adquirir([local], **kw)

    assert r1["copiado"] == ["X.zip"] and r2["ja_presente"] == ["X.zip"] and not r2["copiado"]
    assert sorted(p.name for p in (raiz / "origem" / "indicadores").iterdir()) == ["X.zip"]


def test_adquirir_sem_baixar_nao_faz_requisicao(tmp_path):
    m, raiz = _manifesto(tmp_path, [("origem", "origem/indicadores/X.zip", CONTEUDO)])
    servidor = ServidorFalso({URL: CONTEUDO})
    r = adquirir([], cliente=_cliente(servidor), manifesto=m, raiz=raiz, cache=tmp_path / "cache")
    assert r["faltando"] == ["X.zip"] and servidor.pedidos == []


def test_adquirir_com_baixar_usa_fallback_quando_a_pagina_nao_carrega(tmp_path, monkeypatch):
    m, raiz = _manifesto(tmp_path, [("origem", "origem/indicadores/X.zip", CONTEUDO)])
    fontes = tmp_path / "fontes.csv"
    fontes.write_text(f"arquivo,url,pagina,atualizado_em,capturado_em\nX.zip,{URL},p,,2026-09-30\n",
                      encoding="utf-8")
    servidor = ServidorFalso({URL: CONTEUDO})   # páginas do INEP dão 404
    r = adquirir([], baixar_da_rede=True, cliente=_cliente(servidor), manifesto=m, raiz=raiz,
                 cache=tmp_path / "cache", fontes_estaticas=fontes, descoberta=tmp_path / "desc.json")
    assert r["baixado"] == ["X.zip"]
    assert (raiz / "origem" / "indicadores" / "X.zip").read_bytes() == CONTEUDO
    assert (tmp_path / "desc.json").exists()

    pedidos = len(servidor.pedidos)
    adquirir([], baixar_da_rede=True, cliente=_cliente(servidor), manifesto=m, raiz=raiz,
             cache=tmp_path / "cache", fontes_estaticas=fontes, descoberta=tmp_path / "desc.json")
    assert len(servidor.pedidos) == pedidos   # idempotente: nada é pedido de novo


def test_verificar_manifesto_externo_ausente_e_aviso(tmp_path):
    m, raiz = _manifesto(tmp_path, [
        ("origem", "origem/indicadores/X.zip", CONTEUDO),
        ("externo", "externo/base_longitudinal_v1/base.csv", b"base"),
    ])
    (raiz / "origem" / "indicadores").mkdir(parents=True)
    (raiz / "origem" / "indicadores" / "X.zip").write_bytes(CONTEUDO)
    erros, avisos = verificar_manifesto(m, raiz)
    assert erros == [] and len(avisos) == 1 and avisos[0].startswith("falta externo/base_longitudinal_v1/base.csv")

    (raiz / "origem" / "indicadores" / "X.zip").write_bytes(b"adulterado")
    erros, _ = verificar_manifesto(m, raiz)
    assert len(erros) == 1 and "sha256 diverge" in erros[0]


def test_link_e_imutavel():
    lk = Link("a.zip", "u", "p", None)
    with pytest.raises(AttributeError):
        lk.url = "outra"  # type: ignore[misc]
