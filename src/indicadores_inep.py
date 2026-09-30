"""Localização e perfil das planilhas de indicadores do INEP já extraídas por
src/extrair_brutos_inep.py em dados/bruto/indicadores/{tipo}/{ano}/.

Layout observado em todas as planilhas (uma aba por arquivo): linhas de título
e cabeçalho humano no topo, depois UMA linha com os nomes técnicos das colunas
(começa por 'NU_ANO_CENSO' ou 'Ano'/'ano' e é imediatamente seguida pela
primeira linha de dados, cuja 1ª célula é o ano numérico), depois os dados.
A posição dessa linha varia por indicador e ano, por isso é detectada, nunca
fixada. Ausência é grafada como a string '--'. Nos níveis municípios e
Brasil/UF há várias linhas por unidade (Localização × Dependência); só no
nível escolas há uma linha por escola.
"""
from __future__ import annotations

import csv
import logging
import pathlib
from dataclasses import dataclass, field

import openpyxl

from src.config import DADOS, DOCS, EXTRACAO_INDICADORES, INDICADORES

logger = logging.getLogger(__name__)

TIPOS = ("tx_rend", "TDI", "ATU", "IED", "HAD")
NIVEIS = ("brasil_regioes_ufs", "municipios", "escolas")
ANOS = range(2019, 2026)
MARCADOR_AUSENTE = "--"

# Nome do .xlsx dentro da pasta tipo/ano, por geração de nomenclatura.
_NOME_XLSX = {
    "tx_rend": "tx_rend_{nivel}_{ano}.xlsx",
    "padrao_a": "{tipo}_{NIVEL}_{ano}.xlsx",
}

_INICIOS_CABECALHO = {"nu_ano_censo", "ano"}
_UF_RR = {"SG_UF": "RR", "UNIDGEO": "Roraima"}


def caminho_indicador(tipo: str, ano: int, nivel: str) -> pathlib.Path:
    """Path do .xlsx de (tipo, ano, nivel); ValueError/FileNotFoundError úteis."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo {tipo!r} desconhecido. Tipos: {list(TIPOS)}")
    if nivel not in NIVEIS:
        raise ValueError(f"Nível {nivel!r} desconhecido. Níveis: {list(NIVEIS)}")
    padrao = _NOME_XLSX["tx_rend" if tipo == "tx_rend" else "padrao_a"]
    p = INDICADORES / tipo / str(ano) / padrao.format(
        tipo=tipo, nivel=nivel, NIVEL=nivel.upper(), ano=ano
    )
    if not p.exists():
        existentes = sorted(
            q.relative_to(INDICADORES).as_posix()
            for q in INDICADORES.glob(f"{tipo}/*/*.xlsx")
        )
        raise FileNotFoundError(
            f"Indicador ({tipo!r}, {ano}, {nivel!r}) não está extraído em {p}.\n"
            f"Se o .zip existe em dados/origem/indicadores/, rode "
            f"`python -m src.extrair_brutos_inep`; senão, baixar arquivo novo é "
            f"decisão da pesquisadora (CLAUDE.md §6).\n"
            f"Arquivos de {tipo} disponíveis: {existentes}"
        )
    return p


def listar_extraidos() -> list[tuple[str, int, str, pathlib.Path]]:
    """[(tipo, ano, nivel, path)] de todo .xlsx sob INDICADORES, via
    docs/extracao_indicadores.csv."""
    manifesto = EXTRACAO_INDICADORES
    if not manifesto.exists():
        raise FileNotFoundError(
            f"Relação de extração não encontrada: {manifesto}\n"
            f"Rode `python -m src.extrair_brutos_inep` primeiro."
        )
    itens = []
    with manifesto.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["acao"] == "extraido" and r["arquivo_extraido"].endswith(".xlsx"):
                itens.append((r["tipo"], int(r["ano"]), r["nivel"], DADOS / r["arquivo_extraido"]))
    return sorted(itens)


@dataclass
class PerfilPlanilha:
    tipo: str
    ano: int
    nivel: str
    arquivo: str
    planilha: str
    n_abas: int
    linha_cabecalho: int          # 1-based, linha dos nomes técnicos (0 = não existe)
    linha_cabecalho_humano: int = 0   # 1-based, 1ª linha do cabeçalho humano
    colunas: list[str] = field(default_factory=list)
    descricoes: list[str] = field(default_factory=list)  # rótulos humanos unidos por ' › '
    n_celulas_dados: int = 0      # células preenchidas (até a última) na 1ª linha de dados
    n_linhas_dados: int = 0       # linhas cuja 1ª célula é o ano do censo
    n_linhas_rr: int = 0          # dessas, com SG_UF == 'RR'
    n_entidades_distintas: int | None = None  # CO_ENTIDADE distintos (só nível escolas)
    n_linhas_rodape: int = 0      # linhas não vazias após o cabeçalho que não são dados
    anos_na_coluna_ano: str = ""  # valores distintos vistos na 1ª coluna

    @property
    def n_colunas(self) -> int:
        return len(self.colunas)


def _aparar(row: tuple) -> list:
    """Remove só as células vazias do FIM da linha, preservando posições internas."""
    fim = len(row)
    while fim and row[fim - 1] is None:
        fim -= 1
    return list(row[:fim])


def _nomes_posicionais(row: tuple) -> list[str]:
    """Nomes técnicos por posição; célula interna vazia vira '_SEM_NOME_{pos}'
    em vez de ser descartada, para que desalinhamentos apareçam no inventário."""
    return [
        str(c).strip() if c is not None else f"_SEM_NOME_{pos}"
        for pos, c in enumerate(_aparar(row), start=1)
    ]


def _eh_inicio_cabecalho(celula) -> bool:
    return isinstance(celula, str) and celula.strip().lower() in _INICIOS_CABECALHO


def _descricoes_humanas(linhas: list[tuple], n_colunas: int) -> list[str]:
    """Descrição de cada coluna a partir do bloco de cabeçalho humano (várias
    linhas, com células mescladas que chegam como None). Cada linha é
    preenchida para a direita (célula mesclada herda o rótulo à esquerda) e os
    rótulos das linhas são unidos com ' › '."""
    niveis: list[list[str | None]] = []
    for linha in linhas:
        atual: str | None = None
        preenchida: list[str | None] = []
        for pos in range(n_colunas):
            # o preenchimento à direita não atravessa a fronteira de um grupo
            # definido nas linhas de cima (ex.: 'Anos Finais' não vaza para o
            # bloco 'Ensino Médio')
            if pos and any(n[pos] != n[pos - 1] for n in niveis):
                atual = None
            c = linha[pos] if pos < len(linha) else None
            if c is not None:
                atual = " ".join(str(c).split())
            preenchida.append(atual)
        niveis.append(preenchida)
    descricoes = []
    for pos in range(n_colunas):
        partes: list[str] = []
        for nivel in niveis:
            rotulo = nivel[pos]
            if rotulo and (not partes or partes[-1] != rotulo):
                partes.append(rotulo)
        descricoes.append(" › ".join(partes))
    return descricoes


def _interpretar_cabecalho(perfil: PerfilPlanilha, buffer: list[tuple[int, tuple]], primeira_dados: tuple) -> None:
    """`buffer` são as linhas antes da 1ª linha de dados. A linha de nomes
    técnicos, se existir, é a última do buffer e começa por Ano/NU_ANO_CENSO;
    o bloco humano vai da primeira linha que começa por 'Ano' até antes dela.
    Sem linha técnica (tx_rend municípios 2019), os nomes são sintéticos."""
    perfil.n_celulas_dados = len(_aparar(primeira_dados))
    nao_vazias = [(i, r) for i, r in buffer if any(c is not None for c in r)]
    ultima = buffer[-1] if buffer else None
    if ultima is not None and _eh_inicio_cabecalho(ultima[1][0]):
        perfil.linha_cabecalho = ultima[0]
        perfil.colunas = _nomes_posicionais(ultima[1])
        humanas = [(i, r) for i, r in nao_vazias if i < ultima[0]]
    else:
        perfil.colunas = [f"_SEM_NOME_{pos}" for pos in range(1, perfil.n_celulas_dados + 1)]
        humanas = nao_vazias
    inicio = next((k for k, (_, r) in enumerate(humanas) if _eh_inicio_cabecalho(r[0])), None)
    if inicio is None:
        perfil.descricoes = [""] * perfil.n_colunas
    else:
        perfil.linha_cabecalho_humano = humanas[inicio][0]
        perfil.descricoes = _descricoes_humanas([r for _, r in humanas[inicio:]], perfil.n_colunas)


def perfilar_planilha(caminho: pathlib.Path, tipo: str, ano: int, nivel: str) -> PerfilPlanilha:
    """Lê a planilha em modo read_only, detecta o cabeçalho (humano e técnico)
    e conta linhas de dados / RR / rodapé sem carregar tudo em memória."""
    wb = openpyxl.load_workbook(caminho, read_only=True)
    try:
        ws = wb.worksheets[0]
        perfil = PerfilPlanilha(tipo, ano, nivel, caminho.name, ws.title, len(wb.sheetnames), 0)
        pos_uf: int | None = None
        valor_rr: str | None = None
        pos_ent: int | None = None
        buffer: list[tuple[int, tuple]] = []
        anos_vistos: set = set()
        entidades: set = set()
        cabecalho_pronto = False
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            primeira = row[0] if row else None
            eh_ano = isinstance(primeira, (int, float)) and 1990 <= primeira <= 2100
            if not cabecalho_pronto:
                if not eh_ano:
                    buffer.append((i, row))
                    continue
                _interpretar_cabecalho(perfil, buffer, row)
                cabecalho_pronto = True
                for nome_col, valor in _UF_RR.items():
                    if nome_col in perfil.colunas:
                        pos_uf, valor_rr = perfil.colunas.index(nome_col), valor
                        break
                if "CO_ENTIDADE" in perfil.colunas:
                    pos_ent = perfil.colunas.index("CO_ENTIDADE")
            if primeira is None:
                if any(c is not None for c in row):
                    perfil.n_linhas_rodape += 1
                continue
            if eh_ano:
                perfil.n_linhas_dados += 1
                anos_vistos.add(int(primeira))
                if pos_uf is not None and row[pos_uf] == valor_rr:
                    perfil.n_linhas_rr += 1
                if pos_ent is not None:
                    entidades.add(row[pos_ent])
            else:
                perfil.n_linhas_rodape += 1
        perfil.anos_na_coluna_ano = ";".join(str(a) for a in sorted(anos_vistos))
        if pos_ent is not None:
            perfil.n_entidades_distintas = len(entidades)
    finally:
        wb.close()

    if not cabecalho_pronto:
        raise ValueError(
            f"Nenhuma linha de dados (1ª célula = ano numérico) encontrada em {caminho.name}."
        )
    if perfil.linha_cabecalho == 0:
        logger.warning("%s: sem linha de nomes técnicos; nomes sintéticos _SEM_NOME_n", caminho.name)
    return perfil


def inventariar(destino_docs: pathlib.Path = DOCS) -> tuple[pathlib.Path, pathlib.Path]:
    """Perfila todas as planilhas extraídas e grava
    docs/inventario_indicadores.csv (uma linha por planilha) e
    docs/presenca_colunas_indicadores.csv (coluna × tipo/nível, anos nas colunas)."""
    perfis: list[PerfilPlanilha] = []
    for tipo, ano, nivel, caminho in listar_extraidos():
        logger.info("Perfilando %s %s %s", tipo, ano, nivel)
        perfis.append(perfilar_planilha(caminho, tipo, ano, nivel))

    destino_docs.mkdir(parents=True, exist_ok=True)
    inv = destino_docs / "inventario_indicadores.csv"
    with inv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "tipo", "ano", "nivel", "arquivo", "planilha", "n_abas", "linha_cabecalho_humano",
            "linha_cabecalho", "n_colunas", "n_celulas_dados", "n_linhas_dados", "n_linhas_rr",
            "n_linhas_rodape", "n_entidades_distintas", "anos_na_coluna_ano", "primeira_coluna",
        ])
        for p in perfis:
            w.writerow([
                p.tipo, p.ano, p.nivel, p.arquivo, p.planilha, p.n_abas, p.linha_cabecalho_humano,
                p.linha_cabecalho, p.n_colunas, p.n_celulas_dados, p.n_linhas_dados, p.n_linhas_rr,
                p.n_linhas_rodape, "" if p.n_entidades_distintas is None else p.n_entidades_distintas,
                p.anos_na_coluna_ano, p.colunas[0],
            ])

    # Presença: valor = posição da coluna naquele ano; descrição = rótulo humano
    # do ano mais recente em que a coluna existe.
    presenca: dict[tuple[str, str, str], dict[int, int]] = {}
    descricao: dict[tuple[str, str, str], tuple[int, str]] = {}
    ordem: dict[tuple[str, str, str], int] = {}
    for p in perfis:
        for pos, (col, desc) in enumerate(zip(p.colunas, p.descricoes)):
            chave = (p.tipo, p.nivel, col)
            presenca.setdefault(chave, {})[p.ano] = pos + 1
            ordem.setdefault(chave, pos)
            if desc and (chave not in descricao or p.ano > descricao[chave][0]):
                descricao[chave] = (p.ano, desc)
    pres = destino_docs / "presenca_colunas_indicadores.csv"
    with pres.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tipo", "nivel", "coluna", "descricao", *[str(a) for a in ANOS], "n_anos"])
        for chave in sorted(presenca, key=lambda k: (k[0], k[1], ordem[k])):
            anos = presenca[chave]
            w.writerow([*chave, descricao.get(chave, (0, ""))[1], *[anos.get(a, "") for a in ANOS], len(anos)])

    return inv, pres


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inv, pres = inventariar()
    logger.info("Gravados %s e %s", inv, pres)
