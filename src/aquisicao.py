"""Aquisição dos dados do INEP: descoberta dos links, download ou cópia local
dos zips para dados/origem/ e extração para dados/bruto/.

Cria em dados/origem/ e dados/bruto/ só o que não existe (CLAUDE.md §3,
regra 1): todo arquivo passa por src/integridade.py (temporário → hash
conferido → renomeio). A especificação do que obter é dados/MANIFEST.csv:
só se baixa ou copia o que está nele, e o sha256 dele é o teste.

Camadas:
- descoberta: raspa a página de microdados e, nos indicadores, índice →
  página do indicador → aba de cada ano (atributo data-url). Grava
  dados/descoberta_inep.json (url, arquivo, texto "Atualizado em", data da
  raspagem) e o HTML em dados/cache_download/html/{data}/. Compara com o
  fallback estático versionado (src/fontes_inep.csv) e avisa divergências.
- obtenção: cópia de pastas locais (--origem-local) ou download (--baixar),
  idempotente, com retomada por HTTP Range + If-Range e progresso via tqdm.
- extração: dos zips de microdados sai só o que o projeto usa, com o nome
  exato do INEP (inclusive o `.CSV` maiúsculo de 2020): o arquivo de escolas
  de cada ano e, em 2025, também Turma, Matrícula e Docente; e os dois PDFs
  de documentação. Os zips de indicadores são extraídos por
  src/extrair_brutos_inep.py.

Sem --baixar, nenhuma requisição de rede é feita.

Fatos dos zips e das páginas que o código trata (verificados em 2026-09-29/30):
- a pasta interna dos zips de microdados muda a cada ano, e até 2023 o nome
  vem em cp437 com acento corrompido — o membro é localizado pelo nome-base;
- o md5_*.txt do INEP diverge na caixa do nome (".csv" para ".CSV" em 2020,
  "_v2.csv" para "_V2.csv" em 2025) — a comparação ignora caixa;
- nas páginas de indicador, o data-id da aba nem sempre é um ano: IED tem a
  aba "Sobre", e em tx_rend a aba de 2021 tem data-id "2021." (com ponto).
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import logging
import pathlib
import re
import shutil
import time
import urllib.parse
import zipfile
from typing import Protocol

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.config import (
    ARQUIVOS,
    CACHE_DOWNLOAD,
    DADOS,
    MANIFEST,
    ORIGEM_CENSO,
    ORIGEM_DOC,
)
from src.integridade import (
    ErroIntegridade,
    Referencia,
    _para_divergente,
    confere_existente,
    digestos,
    gravar_conferido,
    hashes_manifesto,
    md5_do_zip,
    promover,
    sha256_arquivo,
)

logger = logging.getLogger(__name__)

# Nome do zip de microdados de cada ano, como publicado pelo INEP. 2025 tem o
# underscore extra no fim.
MICRODADOS_ZIP: dict[int, str] = {
    2019: "microdados_censo_escolar_2019.zip",
    2020: "microdados_censo_escolar_2020.zip",
    2021: "microdados_censo_escolar_2021.zip",
    2022: "microdados_censo_escolar_2022.zip",
    2023: "microdados_censo_escolar_2023.zip",
    2024: "microdados_censo_escolar_2024.zip",
    2025: "microdados_censo_escolar_2025_.zip",
}

# Documentação em dados/origem/doc/: nome no projeto → (ano do zip, membro).
# Estes dois nomes NÃO são do INEP — os PDFs foram renomeados à mão em
# 2026-09-15 e o manifesto os registra assim. Nota.pdf é idêntico nos zips de
# 2019, 2020 e 2021; Leia-me.pdf difere por ano, e o registrado é o de 2021.
DOCUMENTACAO: dict[str, tuple[int, str]] = {
    "Leia-me-2021.pdf": (2021, "Leia-me.pdf"),
    "Nota-2021.pdf": (2021, "Nota.pdf"),
}

# ── Páginas do INEP ─────────────────────────────────────────────────────────
BASE_INEP = "https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/"
PAGINA_MICRODADOS = BASE_INEP + "microdados/censo-escolar"
PAGINA_INDICADORES = BASE_INEP + "indicadores-educacionais"
# Tipo do indicador → último segmento da URL da sua página (lido do índice em
# 2026-09-30). A URL real vem do índice; o slug só identifica o link.
PAGINAS_INDICADOR: dict[str, str] = {
    "ATU": "media-de-alunos-por-turma",
    "HAD": "media-de-horas-aula-diaria",
    "IED": "esforco-docente",
    "TDI": "taxas-de-distorcao-idade-serie",
    "tx_rend": "taxas-de-rendimento-escolar",
}

USER_AGENT = "abandono-escolar-rr/0.1 (pesquisa academica PIBIC/UERR; reproducao de dados abertos)"
FONTES_ESTATICAS = pathlib.Path(__file__).with_name("fontes_inep.csv")
DESCOBERTA_JSON = DADOS / "descoberta_inep.json"
HTML_CACHE = CACHE_DOWNLOAD / "html"

_ANO_ABA = re.compile(r"(\d{4})\.?")
_ATUALIZADO_ABA = re.compile(r"Atualizado em\s*(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}h\d{2})?)")
_ATUALIZADO_ITEM = re.compile(r"\(([^()]*atualizad[oa] em[^()]*)\)", re.IGNORECASE)


class ErroAquisicao(RuntimeError):
    """Arquivo do manifesto que não pôde ser obtido nem localmente nem da rede."""


@dataclasses.dataclass(frozen=True)
class Link:
    arquivo: str                  # nome do zip, como publicado
    url: str
    pagina: str                   # página onde o link foi achado
    atualizado_em: str | None     # texto "Atualizado em ..." da página/item, literal


# ── Extração (zips de microdados) ───────────────────────────────────────────

def _localizar_membro(zf: zipfile.ZipFile, nome: str, zip_path: pathlib.Path) -> zipfile.ZipInfo:
    achados = [
        i for i in zf.infolist()
        if not i.is_dir() and pathlib.PurePosixPath(i.filename).name == nome
    ]
    if len(achados) == 1:
        return achados[0]
    existentes = sorted(
        pathlib.PurePosixPath(i.filename).name for i in zf.infolist() if not i.is_dir()
    )
    raise ErroIntegridade(
        f"{'Nenhum' if not achados else len(achados)} membro chamado {nome!r} em "
        f"{zip_path.name}.\nArquivos no zip: {existentes}"
    )


def extrair_membro(
    zip_path: pathlib.Path, membro: str, destino: pathlib.Path, sha_esperado: str,
    *, sobrescrever: bool = False,
) -> str:
    """Extrai `membro` (nome-base) de `zip_path` para `destino`, conferido
    contra `sha_esperado` (manifesto) e o md5 do INEP. Retorna o status de
    `gravar_conferido`: "ja_presente", "extraido" ou "sobrescrito"."""
    # Confere o existente sem abrir o zip: o zip pode nem estar mais no disco.
    if not sobrescrever and confere_existente(destino, Referencia(sha_esperado)) is not None:
        logger.debug("Já presente e íntegro, não tocado: %s", destino.name)
        return "ja_presente"
    if not zip_path.exists():
        existentes = sorted(p.name for p in zip_path.parent.glob("*.zip")) if zip_path.parent.is_dir() else []
        raise FileNotFoundError(
            f"Zip não encontrado: {zip_path}\nZips em {zip_path.parent}: {existentes or 'nenhum'}"
        )
    with zipfile.ZipFile(zip_path) as zf:
        info = _localizar_membro(zf, membro, zip_path)
        # Caixa ignorada DE PROPÓSITO (CLAUDE.md §7): o .txt de md5 do INEP grafa o
        # nome com outra caixa ('.csv' para '.CSV' em 2020, '_v2' para '_V2' em 2025,
        # '.xlsX' em HAD municípios 2019–2021). O arquivo em si é localizado pelo nome exato.
        ref = Referencia(sha_esperado, md5_do_zip(zf).get(membro.lower()), info.CRC)
        with zf.open(info) as fonte:
            status = gravar_conferido(fonte, destino, ref, sobrescrever=sobrescrever,
                                      descricao=f"de {zip_path.name}").status
    logger.info("%s: %s <- %s", status, destino.name, zip_path.name)
    return status


def extrair_censo(
    ano: int, origem: pathlib.Path = ORIGEM_CENSO, hashes: dict[str, str] | None = None,
    *, sobrescrever: bool = False,
) -> dict[str, str]:
    """Extrai de origem/censo/ as tabelas de ARQUIVOS do `ano` → {arquivo: status}."""
    if ano not in MICRODADOS_ZIP:
        raise ValueError(f"Ano {ano!r} sem zip de microdados mapeado. Anos: {sorted(MICRODADOS_ZIP)}")
    hashes = hashes if hashes is not None else hashes_manifesto()
    zip_path = origem / MICRODADOS_ZIP[ano]
    status = {}
    for (a, _tabela), destino in sorted(ARQUIVOS.items()):
        if a != ano:
            continue
        if destino.name not in hashes:
            raise ErroIntegridade(f"{destino.name} não está em dados/MANIFEST.csv; nada a conferir.")
        status[destino.name] = extrair_membro(
            zip_path, destino.name, destino, hashes[destino.name], sobrescrever=sobrescrever,
        )
    return status


def extrair_documentacao(
    origem: pathlib.Path = ORIGEM_CENSO, destino: pathlib.Path = ORIGEM_DOC,
    hashes: dict[str, str] | None = None, *, sobrescrever: bool = False,
) -> dict[str, str]:
    """Extrai os PDFs de DOCUMENTACAO dos zips de microdados → {arquivo: status}."""
    hashes = hashes if hashes is not None else hashes_manifesto()
    return {
        nome: extrair_membro(origem / MICRODADOS_ZIP[ano], membro, destino / nome,
                             hashes[nome], sobrescrever=sobrescrever)
        for nome, (ano, membro) in DOCUMENTACAO.items()
    }


# ── HTTP ────────────────────────────────────────────────────────────────────

class Sessao(Protocol):
    def get(self, url: str, **kwargs) -> requests.Response: ...


class ClienteInep:
    """GET com User-Agent identificável, pausa entre requisições e novas
    tentativas com espera exponencial em erro de conexão, 429 e 5xx."""

    def __init__(self, sessao: Sessao | None = None, *, pausa: float = 1.5,
                 tentativas: int = 4, espera_base: float = 2.0):
        if sessao is None:
            sessao = requests.Session()
            sessao.headers["User-Agent"] = USER_AGENT
        self.sessao, self.pausa = sessao, pausa
        self.tentativas, self.espera_base = tentativas, espera_base
        self._ultima = 0.0

    def get(self, url: str, *, headers: dict | None = None, stream: bool = False) -> requests.Response:
        erro: Exception | None = None
        for t in range(self.tentativas):
            espera = self.pausa - (time.monotonic() - self._ultima) if t == 0 else self.espera_base * 2 ** (t - 1)
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.monotonic()
            try:
                r = self.sessao.get(url, headers=headers or {}, stream=stream, timeout=60)
            except requests.RequestException as e:
                erro = e
                logger.warning("Tentativa %d/%d falhou para %s: %s", t + 1, self.tentativas, url, e)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                erro = requests.HTTPError(f"HTTP {r.status_code}")
                logger.warning("Tentativa %d/%d: HTTP %d em %s", t + 1, self.tentativas, r.status_code, url)
                continue
            r.raise_for_status()
            return r
        raise ErroAquisicao(f"{url} falhou após {self.tentativas} tentativas: {erro}")


class SessaoCapturada:
    """Serve páginas capturadas (dados/cache_download/html/{data}/ ou fixtures
    de teste) no lugar da rede: URL → <pasta>/<caminho da URL>.html. Permite
    reexaminar uma captura sem nova raspagem."""

    def __init__(self, pasta: pathlib.Path):
        self.pasta = pasta
        self.pedidos: list[str] = []

    def get(self, url: str, **_kwargs) -> requests.Response:
        self.pedidos.append(url)
        r = requests.Response()
        arquivo = self.pasta / (url.removeprefix(BASE_INEP).rstrip("/") + ".html")
        r.url = url
        if url.startswith(BASE_INEP) and arquivo.exists():
            r.status_code, r._content, r.encoding = 200, arquivo.read_bytes(), "utf-8"
        else:
            r.status_code, r._content = 404, b""
        return r


# ── Descoberta ──────────────────────────────────────────────────────────────

def _nome_do_link(href: str) -> str:
    return urllib.parse.unquote(pathlib.PurePosixPath(urllib.parse.urlparse(href).path).name)


def _links_zip(soup: BeautifulSoup) -> list:
    return [a for a in soup.find_all("a", href=True)
            if urllib.parse.urlparse(a["href"]).path.endswith(".zip")]


def parse_microdados(html: str, pagina: str = PAGINA_MICRODADOS) -> list[Link]:
    """Links .zip da página de microdados; a nota de atualização fica entre
    parênteses no mesmo item de lista ("(Atualizado em 8/3/2023)",
    "(Documento atualizado em julho/2026)")."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in _links_zip(soup):
        item = a.find_parent("li") or a
        m = _ATUALIZADO_ITEM.search(item.get_text(" ", strip=True))
        links.append(Link(_nome_do_link(a["href"]), a["href"], pagina, m.group(1) if m else None))
    return links


def parse_indice(html: str) -> dict[str, str]:
    """{tipo: URL da página do indicador} a partir do índice de indicadores."""
    soup = BeautifulSoup(html, "html.parser")
    achados: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        caminho = urllib.parse.urlparse(a["href"]).path.rstrip("/")
        for tipo, slug in PAGINAS_INDICADOR.items():
            if caminho.endswith("/indicadores-educacionais/" + slug):
                achados.setdefault(tipo, a["href"])
    return achados


def parse_abas(html: str) -> dict[int, str]:
    """{ano: URL da aba} de uma página de indicador. Abas cujo data-id não é
    um ano (ex.: "Sobre") são ignoradas; "2021." vale como 2021."""
    soup = BeautifulSoup(html, "html.parser")
    abas: dict[int, str] = {}
    for el in soup.select("[data-url]"):
        m = _ANO_ABA.fullmatch(el.get("data-id", "").strip())
        if m:
            abas.setdefault(int(m.group(1)), el["data-url"])
    return abas


def parse_aba(html: str, pagina: str) -> list[Link]:
    """Links .zip de uma aba de ano, com o "Atualizado em" da aba, se houver."""
    soup = BeautifulSoup(html, "html.parser")
    m = _ATUALIZADO_ABA.search(soup.get_text(" ", strip=True))
    return [Link(_nome_do_link(a["href"]), a["href"], pagina, m.group(1) if m else None)
            for a in _links_zip(soup)]


def _pagina(cliente: ClienteInep, url: str, cache_html: pathlib.Path | None) -> str:
    """Texto da página (e cópia em `cache_html`). Página que não carrega
    devolve "" com aviso: a descoberta segue e o fallback cobre a lacuna."""
    try:
        texto = cliente.get(url).text
    except (requests.RequestException, ErroAquisicao) as e:
        logger.warning("Página não carregou, seguindo sem ela: %s (%s)", url, e)
        return ""
    if cache_html is not None:
        destino = cache_html / (url.removeprefix(BASE_INEP).rstrip("/") + ".html")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return texto


def descobrir(
    cliente: ClienteInep, anos_por_tipo: dict[str, set[int]],
    cache_html: pathlib.Path | None = None,
) -> list[Link]:
    """Raspa as páginas do INEP e devolve os links .zip encontrados.

    Nos indicadores, só visita as abas dos anos em `anos_por_tipo` (os que o
    manifesto pede). Estrutura que mudou (indicador ou ano não achado) vira
    aviso — o fallback estático cobre a lacuna.
    """
    links = parse_microdados(_pagina(cliente, PAGINA_MICRODADOS, cache_html))
    indice = parse_indice(_pagina(cliente, PAGINA_INDICADORES, cache_html))
    for tipo in sorted(anos_por_tipo):
        if tipo not in indice:
            logger.warning("Indicador %s (%s) não achado no índice %s.",
                           tipo, PAGINAS_INDICADOR.get(tipo), PAGINA_INDICADORES)
            continue
        abas = parse_abas(_pagina(cliente, indice[tipo], cache_html))
        for ano in sorted(anos_por_tipo[tipo]):
            if ano not in abas:
                logger.warning("Aba %d não achada na página de %s; abas: %s", ano, tipo, sorted(abas))
                continue
            links += parse_aba(_pagina(cliente, abas[ano], cache_html), abas[ano])
    return links


def ler_fontes_estaticas(caminho: pathlib.Path = FONTES_ESTATICAS) -> dict[str, Link]:
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as f:
        return {r["arquivo"]: Link(r["arquivo"], r["url"], r["pagina"], r["atualizado_em"] or None)
                for r in csv.DictReader(f)}


def gravar_fontes_estaticas(links: dict[str, Link], capturado_em: str,
                            caminho: pathlib.Path = FONTES_ESTATICAS) -> pathlib.Path:
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "url", "pagina", "atualizado_em", "capturado_em"])
        for nome in sorted(links):
            lk = links[nome]
            w.writerow([lk.arquivo, lk.url, lk.pagina, lk.atualizado_em or "", capturado_em])
    return caminho


def consolidar(raspados: list[Link], estaticos: dict[str, Link], necessarios: set[str]) -> dict[str, Link]:
    """{arquivo: Link} para cada necessário: o raspado, ou o estático se a
    raspagem não o achou. Divergência de URL entre os dois é aviso."""
    por_nome = {lk.arquivo: lk for lk in raspados}
    escolhidos: dict[str, Link] = {}
    for nome in sorted(necessarios):
        r, e = por_nome.get(nome), estaticos.get(nome)
        if r and e and r.url != e.url:
            logger.warning("URL de %s mudou em relação ao fallback: %s (antes %s)", nome, r.url, e.url)
        if r is None and e is not None:
            logger.warning("%s não achado na raspagem; usando o fallback estático %s", nome, e.url)
        if r or e:
            escolhidos[nome] = r or e  # type: ignore[assignment]
    return escolhidos


_MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
     "agosto", "setembro", "outubro", "novembro", "dezembro"], start=1)}


def _data_atualizacao(texto: str | None) -> dt.date | None:
    """'31/07/2026 11h52', '8/3/2023', 'Documento atualizado em julho/2026' → data
    (mês sem dia vira o último dia do mês, para não subestimar a revisão)."""
    if not texto:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"([a-zç]+)/(\d{4})", texto.lower())
    if m and m.group(1) in _MESES:
        mes, ano = _MESES[m.group(1)], int(m.group(2))
        prox = dt.date(ano + mes // 12, mes % 12 + 1, 1)
        return prox - dt.timedelta(days=1)
    return None


def comparar_com_manifesto(links: dict[str, Link], linhas: list[dict]) -> list[str]:
    """Linhas propostas para docs/problemas.csv (tipo versionamento) quando o
    INEP declara atualização posterior à data de download do manifesto. Só
    propõe no log — o arquivo é mantido à mão (CLAUDE.md §6)."""
    propostas = []
    for lin in linhas:
        nome = pathlib.PurePosixPath(lin["arquivo"]).name
        lk = links.get(nome)
        atualizado = _data_atualizacao(lk.atualizado_em if lk else None)
        baixado = dt.date.fromisoformat(lin["data_download"])
        if atualizado and atualizado > baixado:
            propostas.append(
                f'P0XX,versionamento,{lin["arquivo"]},"O INEP declara atualização em '
                f'{lk.atualizado_em!s} ({atualizado.isoformat()}), posterior ao download registrado no '
                f'MANIFEST.csv ({baixado.isoformat()}).","{lk.pagina}; dados/descoberta_inep.json",'
                f'"Rebaixar pode trazer outra versão; o sha256 do manifesto vai divergir.",'
                f'"A decidir: manter a versão do manifesto ou adotar a nova e regerar.",aberto'
            )
    for p in propostas:
        logger.warning("Proposta para docs/problemas.csv (colar à mão):\n%s", p)
    return propostas


def gravar_descoberta(links: dict[str, Link], raspados: list[Link], modo: str,
                      caminho: pathlib.Path = DESCOBERTA_JSON) -> pathlib.Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "data_raspagem": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "modo": modo,
        "n_links_raspados": len(raspados),
        "arquivos": [dataclasses.asdict(links[n]) for n in sorted(links)],
    }
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


# ── Obtenção ────────────────────────────────────────────────────────────────

def linhas_manifesto(caminho: pathlib.Path = MANIFEST) -> list[dict]:
    with caminho.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _zips_de_origem(linhas: list[dict]) -> list[dict]:
    """Linhas de origem/ que são zips do INEP (a documentação sai de dentro deles)."""
    return [lin for lin in linhas
            if lin["estagio"] == "origem" and lin["arquivo"].endswith(".zip")]


def copiar_local(fonte: pathlib.Path, destino: pathlib.Path, ref: Referencia,
                 cache: pathlib.Path = CACHE_DOWNLOAD) -> str:
    """Copia `fonte` (fora de dados/, nunca alterada) para `destino` via
    temporário em cache_download/ e conferência de hash."""
    cache.mkdir(parents=True, exist_ok=True)
    temporario = cache / (destino.name + ".parcial")
    shutil.copyfile(fonte, temporario)
    exigir_zip(temporario, destino, f"copiado de {fonte}")
    promover(temporario, destino, ref, descricao=f"copiado de {fonte}")
    logger.info("copiado: %s <- %s", destino.name, fonte)
    return "copiado"


_ASSINATURA_ZIP = b"PK\x03\x04"


def exigir_zip(temporario: pathlib.Path, destino: pathlib.Path, origem: str,
               content_type: str | None = None) -> None:
    """O que chega para virar um .zip de origem/ precisa SER um zip.

    O site do INEP pode devolver uma página HTML no lugar do arquivo
    (bloqueio anti-robô, redirecionamento, link quebrado). O sha256 do
    manifesto já rejeitaria, mas com uma mensagem que não diz o que houve;
    aqui a recusa é explícita e o arquivo recebido vai para divergente/.
    Confere a assinatura do zip e o diretório central (zip truncado)."""
    if destino.suffix != ".zip":
        return
    with temporario.open("rb") as f:
        inicio = f.read(200)
    if inicio.startswith(_ASSINATURA_ZIP) and zipfile.is_zipfile(temporario):
        return
    alvo = _para_divergente(temporario, destino.name, digestos(temporario))
    trecho = inicio[:80].decode("utf-8", errors="replace").replace("\n", " ").strip()
    raise ErroIntegridade(
        f"{destino.name} ({origem}) não é um zip válido"
        f"{f' (Content-Type: {content_type})' if content_type else ''}; "
        f"começa com {trecho!r}. Provável página HTML no lugar do arquivo. "
        f"Guardado em {alvo}, fora de dados/origem/."
    )


class DownloadIncompleto(RuntimeError):
    pass


def baixar(cliente: ClienteInep, url: str, destino: pathlib.Path, ref: Referencia,
           cache: pathlib.Path = CACHE_DOWNLOAD, *, progresso: bool = True) -> str:
    """Baixa `url` para `destino` via cache_download/<nome>.parcial.

    Retoma download interrompido com Range + If-Range (ETag ou Last-Modified
    guardados em <nome>.parcial.json): se o arquivo mudou no servidor, ele
    responde 200 e o download recomeça do zero, sem emendar versões.
    """
    cache.mkdir(parents=True, exist_ok=True)
    parcial = cache / (destino.name + ".parcial")
    meta = cache / (destino.name + ".parcial.json")
    for tentativa in range(cliente.tentativas):
        feito = parcial.stat().st_size if parcial.exists() else 0
        validador = json.loads(meta.read_text(encoding="utf-8")).get("validador") if meta.exists() else None
        headers = {"Range": f"bytes={feito}-", "If-Range": validador} if feito and validador else {}
        try:
            r = cliente.get(url, headers=headers, stream=True)
            if r.status_code == 206 and r.headers.get("Content-Range", "").startswith(f"bytes {feito}-"):
                modo, inicio = "ab", feito
            else:
                modo, inicio = "wb", 0
            content_type = r.headers.get("Content-Type")
            novo_validador = r.headers.get("ETag") or r.headers.get("Last-Modified")
            meta.write_text(json.dumps({"url": url, "validador": novo_validador}), encoding="utf-8")
            tamanho = r.headers.get("Content-Length")
            total = inicio + int(tamanho) if tamanho else None
            with parcial.open(modo) as f, tqdm(total=total, initial=inicio, unit="B", unit_scale=True,
                                               desc=destino.name, disable=not progresso) as barra:
                for bloco in r.iter_content(1 << 20):
                    f.write(bloco)
                    barra.update(len(bloco))
            if total is not None and parcial.stat().st_size != total:
                raise DownloadIncompleto(f"{parcial.stat().st_size} de {total} bytes")
            break
        except (requests.RequestException, DownloadIncompleto) as e:
            resposta = getattr(e, "response", None)
            if resposta is not None and resposta.status_code == 416:
                # Range inválido para o arquivo atual: recomeça do zero.
                parcial.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
            logger.warning("Download de %s interrompido (tentativa %d/%d): %s — retomando",
                           destino.name, tentativa + 1, cliente.tentativas, e)
            time.sleep(cliente.espera_base * 2 ** tentativa)
    else:
        raise ErroAquisicao(f"Download de {url} não completou após {cliente.tentativas} tentativas.")
    exigir_zip(parcial, destino, f"baixado de {url}", content_type)
    promover(parcial, destino, ref, descricao=f"baixado de {url}")
    meta.unlink(missing_ok=True)
    logger.info("baixado: %s <- %s", destino.name, url)
    return "baixado"


def adquirir(
    origens_locais: list[pathlib.Path] | None = None, *, baixar_da_rede: bool = False,
    cliente: ClienteInep | None = None, manifesto: pathlib.Path = MANIFEST,
    raiz: pathlib.Path = DADOS, cache: pathlib.Path = CACHE_DOWNLOAD,
    fontes_estaticas: pathlib.Path = FONTES_ESTATICAS, descoberta: pathlib.Path = DESCOBERTA_JSON,
) -> dict[str, list[str]]:
    """Obtém para dados/origem/ todo zip do manifesto que falta: primeiro das
    `origens_locais`, depois (só com `baixar_da_rede`) do INEP. Nunca obtém
    arquivo fora do manifesto. Retorna {status: [arquivos]}; "faltando" lista
    o que não foi obtido."""
    origens_locais = origens_locais or []
    linhas = _zips_de_origem(linhas_manifesto(manifesto))
    resultado: dict[str, list[str]] = {"ja_presente": [], "copiado": [], "baixado": [], "faltando": []}
    faltam = []
    for lin in linhas:
        destino, ref = raiz / lin["arquivo"], Referencia(lin["sha256"])
        if confere_existente(destino, ref) is not None:
            resultado["ja_presente"].append(destino.name)
            continue
        fonte = next((d / destino.name for d in origens_locais if (d / destino.name).exists()), None)
        if fonte is not None:
            resultado[copiar_local(fonte, destino, ref, cache)].append(destino.name)
        else:
            faltam.append(lin)

    if faltam and baixar_da_rede:
        cliente = cliente or ClienteInep()
        anos_por_tipo: dict[str, set[int]] = {}
        for lin in faltam:
            m = re.fullmatch(r"indicador_(.+)_(brasil_regioes_ufs|municipios|escolas)", lin["tabela"])
            if m:
                anos_por_tipo.setdefault(m.group(1), set()).add(int(lin["ano"]))
        data = dt.datetime.now().astimezone().date().isoformat()
        raspados = descobrir(cliente, anos_por_tipo, cache / "html" / data)
        necessarios = {pathlib.PurePosixPath(lin["arquivo"]).name for lin in faltam}
        links = consolidar(raspados, ler_fontes_estaticas(fontes_estaticas), necessarios)
        gravar_descoberta(links, raspados, "rede", descoberta)
        comparar_com_manifesto(links, faltam)
        for lin in faltam:
            destino, ref = raiz / lin["arquivo"], Referencia(lin["sha256"])
            if destino.name in links:
                resultado[baixar(cliente, links[destino.name].url, destino, ref, cache)].append(destino.name)
            else:
                resultado["faltando"].append(destino.name)
    else:
        resultado["faltando"] += [pathlib.PurePosixPath(lin["arquivo"]).name for lin in faltam]

    logger.info("Zips de origem/: %d já presentes, %d copiados, %d baixados, %d faltando.",
                *(len(resultado[k]) for k in ("ja_presente", "copiado", "baixado", "faltando")))
    if resultado["faltando"]:
        logger.error("Faltam %d zip(s) do manifesto: %s\nUse --origem-local DIR (pasta com os zips) "
                     "ou --baixar (rede).", len(resultado["faltando"]), resultado["faltando"])
    return resultado


def verificar_manifesto(manifesto: pathlib.Path = MANIFEST, raiz: pathlib.Path = DADOS
                        ) -> tuple[list[str], list[str]]:
    """Confere cada linha do manifesto no disco → (erros, avisos).

    origem/ e bruto/: ausência ou hash divergente é erro (regra 1).
    externo/: ausência é aviso (dado de terceiro, CLAUDE.md §2.3); hash
    divergente é erro. processado/: regenerável — ausência e divergência são
    avisos; divergência quer dizer "a saída mudou", não "o dado foi violado"."""
    erros, avisos = [], []
    for lin in linhas_manifesto(manifesto):
        p, estagio = raiz / lin["arquivo"], lin["estagio"]
        if not p.exists():
            if estagio == "externo":
                avisos.append(f"falta {lin['arquivo']} (dado externo, entregue pelo orientador; "
                              f"não obtenível do INEP)")
            elif estagio == "processado":
                avisos.append(f"falta {lin['arquivo']} (regenerável: python -m src.base_longitudinal)")
            else:
                erros.append(f"falta {lin['arquivo']}")
            continue
        obtido = sha256_arquivo(p)
        if obtido == lin["sha256"]:
            continue
        msg = f"sha256 diverge em {lin['arquivo']}: esperado {lin['sha256']}, obtido {obtido}"
        if estagio == "processado":
            avisos.append(msg + " — a saída regerada mudou em relação à registrada")
        else:
            erros.append(msg)
    for a in avisos:
        logger.warning("Manifesto: %s", a)
    for e in erros:
        logger.error("Manifesto: %s", e)
    return erros, avisos


def main() -> None:
    ap = argparse.ArgumentParser(description="Obtém os zips do manifesto e extrai os microdados.")
    ap.add_argument("--origem-local", type=pathlib.Path, action="append", default=[], metavar="DIR",
                    help="pasta com zips já baixados (repetível); nunca é alterada")
    ap.add_argument("--baixar", action="store_true",
                    help="permite baixar do INEP o que faltar (sem isso, nenhuma requisição de rede)")
    ap.add_argument("--descobrir-do-cache", metavar="AAAA-MM-DD",
                    help="só reexamina a captura de páginas dessa data, sem rede, e regrava src/fontes_inep.csv")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="regrava arquivos extraídos já presentes (CLAUDE.md §3, regra 1)")
    args = ap.parse_args()

    if args.descobrir_do_cache:
        pasta = HTML_CACHE / args.descobrir_do_cache
        linhas = _zips_de_origem(linhas_manifesto())
        anos: dict[str, set[int]] = {}
        for lin in linhas:
            m = re.fullmatch(r"indicador_(.+)_(brasil_regioes_ufs|municipios|escolas)", lin["tabela"])
            if m:
                anos.setdefault(m.group(1), set()).add(int(lin["ano"]))
        raspados = descobrir(ClienteInep(SessaoCapturada(pasta), pausa=0), anos)
        necessarios = {pathlib.PurePosixPath(lin["arquivo"]).name for lin in linhas}
        links = consolidar(raspados, {}, necessarios)
        faltam = sorted(necessarios - links.keys())
        if faltam:
            logger.warning("Não achados na captura de %s: %s", args.descobrir_do_cache, faltam)
        gravar_descoberta(links, raspados, f"cache {args.descobrir_do_cache}")
        logger.info("Gravado %s (%d arquivos)", gravar_fontes_estaticas(links, args.descobrir_do_cache), len(links))
        return

    resultado = adquirir(args.origem_local, baixar_da_rede=args.baixar)
    if resultado["faltando"]:
        raise SystemExit(1)
    extrair_microdados(sobrescrever=args.sobrescrever)


def extrair_microdados(*, sobrescrever: bool = False) -> None:
    """Extrai de origem/censo/ todas as tabelas de ARQUIVOS e os PDFs de
    DOCUMENTACAO. Arquivo já presente e íntegro é conferido sem abrir o zip."""
    hashes = hashes_manifesto()
    status: dict[str, str] = {}
    for ano in sorted(MICRODADOS_ZIP):
        status |= extrair_censo(ano, hashes=hashes, sobrescrever=sobrescrever)
    status |= extrair_documentacao(hashes=hashes, sobrescrever=sobrescrever)
    contagem = {s: list(status.values()).count(s) for s in sorted(set(status.values()))}
    logger.info("Microdados e documentação: %s", contagem)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
