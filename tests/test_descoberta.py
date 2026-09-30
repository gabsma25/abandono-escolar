"""Parser das páginas do INEP contra HTML real capturado — sem rede.

As fixtures ficam em tests/fixtures/html/<data da captura>/, com o caminho da
URL e um capturas.csv (url, data, sha256). Se um teste daqui quebrar, compare
com uma captura nova (python -m src.aquisicao --baixar grava as páginas em
dados/cache_download/html/<data>/): se a página nova difere da fixture, o INEP
mudou o layout; se não difere, o parser regrediu.

Escolha por variação estrutural (levantamento de 2026-09-30 nas 42 páginas):
- as 5 páginas de indicador têm o mesmo layout (div.tab-content[data-url]);
  guardamos esforco-docente (aba "Sobre", URL de 2014 termina em "2014-1") e
  taxas-de-rendimento-escolar (aba de 2021 com data-id "2021.");
- as 35 abas de ano têm o mesmo layout (3 links .zip em ul > li); variam só
  em ter ou não "Atualizado em": guardamos tx_rend 2021 (tem) e 2024 (não tem);
- a página de microdados tem uma forma só.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import logging
import pathlib

import pytest

from src.aquisicao import (
    BASE_INEP,
    PAGINA_INDICADORES,
    PAGINA_MICRODADOS,
    ClienteInep,
    Link,
    SessaoCapturada,
    _data_atualizacao,
    comparar_com_manifesto,
    consolidar,
    descobrir,
    parse_aba,
    parse_abas,
    parse_indice,
    parse_microdados,
)

CAPTURA = pathlib.Path(__file__).parent / "fixtures" / "html" / "2026-09-30"
TX_REND = PAGINA_INDICADORES + "/taxas-de-rendimento-escolar"


def _html(caminho_url: str) -> str:
    return (CAPTURA / (caminho_url + ".html")).read_text(encoding="utf-8")


def test_fixtures_conferem_com_o_registro_de_captura():
    with (CAPTURA / "capturas.csv").open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == 6
    for r in linhas:
        assert r["data_captura"] == CAPTURA.name
        assert r["url"] == BASE_INEP + r["arquivo"].removesuffix(".html")
        assert hashlib.sha256((CAPTURA / r["arquivo"]).read_bytes()).hexdigest() == r["sha256"]


def test_microdados_links_e_notas_de_atualizacao():
    links = {lk.arquivo: lk for lk in parse_microdados(_html("microdados/censo-escolar"))}
    assert len(links) == 31
    assert links["microdados_censo_escolar_2025_.zip"].url == (
        "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025_.zip")
    assert links["microdados_censo_escolar_2025_.zip"].atualizado_em == "Documento atualizado em julho/2026"
    assert links["microdados_censo_escolar_2021.zip"].atualizado_em == "Atualizado em 8/3/2023"
    # 2024 foi revisado (pasta _defeso, 08/07/2026) sem nota na página.
    assert links["microdados_censo_escolar_2024.zip"].atualizado_em is None
    assert all(lk.pagina == PAGINA_MICRODADOS for lk in links.values())


def test_indice_acha_as_cinco_paginas_de_indicador():
    assert parse_indice(_html("indicadores-educacionais")) == {
        "ATU": PAGINA_INDICADORES + "/media-de-alunos-por-turma",
        "HAD": PAGINA_INDICADORES + "/media-de-horas-aula-diaria",
        "IED": PAGINA_INDICADORES + "/esforco-docente",
        "TDI": PAGINA_INDICADORES + "/taxas-de-distorcao-idade-serie",
        "tx_rend": TX_REND,
    }


def test_abas_com_data_id_irregular():
    abas_tx = parse_abas(_html("indicadores-educacionais/taxas-de-rendimento-escolar"))
    assert abas_tx[2021] == TX_REND + "/2021"          # data-id "2021."
    assert set(range(2007, 2026)) <= abas_tx.keys()
    abas_ied = parse_abas(_html("indicadores-educacionais/esforco-docente"))
    assert abas_ied[2014].endswith("/esforco-docente/2014-1")
    assert all(isinstance(a, int) for a in abas_ied)   # aba "Sobre" ignorada


@pytest.mark.parametrize(("ano", "atualizado"), [(2021, "19/07/2023 14h36"), (2024, None)])
def test_aba_de_ano(ano, atualizado):
    links = parse_aba(_html(f"indicadores-educacionais/taxas-de-rendimento-escolar/{ano}"), f"{TX_REND}/{ano}")
    assert sorted(lk.arquivo for lk in links) == [
        f"tx_rend_brasil_regioes_ufs_{ano}.zip", f"tx_rend_escolas_{ano}.zip", f"tx_rend_municipios_{ano}.zip"]
    assert {lk.atualizado_em for lk in links} == {atualizado}
    assert all(lk.url.startswith(f"https://download.inep.gov.br/informacoes_estatisticas/"
                                 f"indicadores_educacionais/{ano}/") for lk in links)


def test_descobrir_navega_indice_pagina_e_abas_sem_rede(caplog):
    sessao = SessaoCapturada(CAPTURA)
    links = descobrir(ClienteInep(sessao, pausa=0), {"tx_rend": {2021, 2024}, "IED": {2023}})
    nomes = {lk.arquivo for lk in links}
    assert {"tx_rend_escolas_2021.zip", "tx_rend_escolas_2024.zip", "microdados_censo_escolar_2019.zip"} <= nomes
    # A aba de IED 2023 não foi capturada: aviso, e a descoberta segue.
    assert "esforco-docente/2023" in caplog.text
    assert all(u.startswith(BASE_INEP) for u in sessao.pedidos)


def test_consolidar_usa_fallback_e_avisa_url_mudada(caplog):
    raspado = [Link("a.zip", "https://novo/a.zip", "p", None)]
    estatico = {"a.zip": Link("a.zip", "https://antigo/a.zip", "p", None),
                "b.zip": Link("b.zip", "https://antigo/b.zip", "p", None)}
    with caplog.at_level(logging.WARNING):
        r = consolidar(raspado, estatico, {"a.zip", "b.zip", "c.zip"})
    assert r["a.zip"].url == "https://novo/a.zip" and r["b.zip"].url == "https://antigo/b.zip"
    assert "c.zip" not in r
    assert "mudou" in caplog.text and "fallback" in caplog.text


@pytest.mark.parametrize(("texto", "data"), [
    ("31/07/2026 11h52", dt.date(2026, 7, 31)),
    ("Atualizado em 8/3/2023", dt.date(2023, 3, 8)),
    ("Documento atualizado em julho/2026", dt.date(2026, 7, 31)),
    (None, None),
])
def test_data_de_atualizacao(texto, data):
    assert _data_atualizacao(texto) == data


def test_atualizacao_posterior_ao_download_vira_proposta_de_problema():
    links = {"x.zip": Link("x.zip", "u", "pagina", "Atualizado em 10/10/2026")}
    linhas = [{"arquivo": "origem/indicadores/x.zip", "data_download": "2026-09-15"},
              {"arquivo": "origem/indicadores/y.zip", "data_download": "2026-09-15"}]
    propostas = comparar_com_manifesto(links, linhas)
    assert len(propostas) == 1 and ",versionamento,origem/indicadores/x.zip," in propostas[0]
