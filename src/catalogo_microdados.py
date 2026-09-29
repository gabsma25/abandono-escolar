"""Catálogo de TODAS as variáveis dos microdados (dados/bruto/), por arquivo:
prefixo (tipo semântico do INEP), bloco temático inferido do nome, taxa de
preenchimento no Brasil e em RR, nº de valores distintos e exemplos em RR.

Não há dicionário oficial do INEP na pasta, portanto a coluna `descricao`
fica vazia aqui; `bloco` é inferido por regras sobre o nome e serve para
navegar, não como classificação final (essa é `docs/dicionario_anotado.csv`).

Saídas (geradas, nunca digitadas):
  docs/catalogo_variaveis_microdados.csv  — uma linha por coluna × arquivo
  docs/catalogo_variaveis.csv             — uma linha por coluna, presença por
                                            arquivo + estatísticas do arquivo
                                            mais recente em que existe
"""
from __future__ import annotations

import csv
import logging
import pathlib
import re
from dataclasses import dataclass

import duckdb

from src.config import ARQUIVOS, DOCS, caminho
from src.leitura import perfilar_csv

logger = logging.getLogger(__name__)

PREFIXOS = {
    "IN": "binária (0/1)",
    "TP": "categórica codificada",
    "QT": "contagem",
    "CO": "código",
    "NO": "nome/texto",
    "NU": "número",
    "DT": "data",
    "SG": "sigla",
    "DS": "texto livre",
}

# Ordem importa: a primeira regra que casar define o bloco.
_REGRAS_BLOCO: list[tuple[str, str]] = [
    (r"^(NU_ANO_CENSO|CO_ENTIDADE|NO_ENTIDADE|CO_MUNICIPIO|NO_MUNICIPIO|CO_UF|SG_UF|NO_UF|CO_REGIAO|NO_REGIAO|CO_ORGAO_REGIONAL|CO_REDE)$", "identificação e chave"),
    (r"MESORREGIAO|MICRORREGIAO|REGIAO_GEOG|DISTRITO", "geografia (IBGE)"),
    (r"^(DS_ENDERECO|NU_ENDERECO|DS_COMPLEMENTO|NO_BAIRRO|CO_CEP|NU_DDD|NU_TELEFONE)$", "endereço e contato"),
    (r"^(TP_SITUACAO_FUNCIONAMENTO|DT_ANO_LETIVO_)", "situação de funcionamento"),
    (r"^(TP_DEPENDENCIA|TP_CATEGORIA_ESCOLA_PRIVADA|IN_CONVENIADA_PP|TP_CONVENIO|IN_MANT_|TP_REGULAMENTACAO|TP_RESPONSAVEL_REGULAMENTACAO|IN_PODER_PUBLICO_PARCERIA|TP_PODER_PUBLICO_PARCERIA|IN_FORMA_CONT_|CO_ESCOLA_SEDE_VINCULADA|CO_IES_OFERTANTE|NU_CNPJ_)", "dependência administrativa e vínculos"),
    (r"^(TP_LOCALIZACAO|TP_LOCALIZACAO_DIFERENCIADA|IN_VINCULO_)", "localização e vínculo institucional"),
    (r"^(IN_LOCAL_FUNC_|IN_PREDIO_COMPARTILHADO|TP_OCUPACAO_)", "local de funcionamento"),
    (r"^(IN_AGUA_|IN_ENERGIA_|IN_ESGOTO_|IN_LIXO_|IN_TRATAMENTO_LIXO_)", "infraestrutura básica (água, energia, esgoto, lixo)"),
    (r"^IN_ACESSIBILIDADE_|^IN_DEPENDENCIAS_PNE$", "acessibilidade"),
    (r"^(IN_EQUIP_|QT_EQUIP_|IN_COMPUTADOR|QT_COMP|IN_DESKTOP_|QT_DESKTOP_|IN_COMP_PORTATIL|QT_COMP_PORTATIL|IN_TABLET_|QT_TABLET_|IN_INTERNET|IN_ACESSO_INTERNET|IN_ACES_INTERNET|IN_BANDA_LARGA|IN_REDE_LOCAL|TP_REDE_LOCAL|IN_REDES_SOCIAIS)", "equipamentos e tecnologia"),
    (r"^(IN_ALMOXARIFADO|IN_AREA_VERDE|IN_AUDITORIO|IN_BANHEIRO|IN_BIBLIOTECA|IN_COZINHA|IN_DESPENSA|IN_DORMITORIO|IN_LABORATORIO|IN_PATIO|IN_PARQUE_INFANTIL|IN_PISCINA|IN_QUADRA|IN_REFEITORIO|IN_SALA_|IN_SECRETARIA|IN_TERREIRAO|IN_VIVEIRO|IN_LAVANDERIA|IN_BERCARIO|IN_AREA_PLANTIO|QT_SALAS_|IN_SALAS?_|IN_DEPENDENCIAS_OUTRAS)", "dependências físicas"),
    (r"^(IN_PROF_(?!TEC$)|QT_PROF_|QT_FUNCIONARIOS)", "profissionais não docentes"),
    (r"^IN_ALIMENTACAO$", "alimentação escolar"),
    (r"^IN_MATERIAL_", "materiais pedagógicos"),
    (r"^IN_EDUC_AMB", "educação ambiental"),
    (r"^(IN_SERIE_ANO|IN_PERIODOS_SEMESTRAIS|IN_FUNDAMENTAL_CICLOS|IN_GRUPOS_NAO_SERIADOS|IN_MODULOS|IN_FORMACAO_ALTERNANCIA|TP_PROPOSTA_PEDAGOGICA|TP_AEE|TP_ATIVIDADE_COMPLEMENTAR|IN_EXAME_SELECAO|IN_RESERVA_|IN_ORGAO_|IN_BRASIL_ALFABETIZADO|IN_FINAL_SEMANA|TP_ITINERARIO_FORMATIVO|IN_ITINERARIO_)", "organização do ensino e gestão"),
    (r"^(IN_EDUCACAO_INDIGENA|TP_INDIGENA_LINGUA|CO_LINGUA_INDIGENA)", "educação indígena"),
    (r"^(IN_DIURNO|IN_NOTURNO|IN_EAD|IN_BAS|IN_INF|IN_FUND|IN_MED|IN_PROF$|IN_PROF_TEC|IN_EJA|IN_ESP|IN_REGULAR|IN_ESCOLARIZACAO|IN_COMUM_|IN_ESPECIAL_EXCLUSIVA|IN_PROFISSIONALIZANTE|IN_INTEGRAL)", "oferta (etapas, modalidades, turnos)"),
    (r"^IN_TIPO_ATEND_", "tipo de atendimento (escolarização, AEE, AC)"),
    (r"^QT_TRANSP_", "transporte escolar"),
    (r"^QT_MAT_", "matrículas"),
    (r"^QT_DOC_", "docentes"),
    (r"^QT_TUR_", "turmas"),
]


@dataclass
class VariavelArquivo:
    rotulo: str
    ano: int
    tabela: str
    posicao: int
    coluna: str
    prefixo: str
    tipo_semantico: str
    bloco: str
    n_linhas_br: int
    n_preenchido_br: int
    n_linhas_rr: int
    n_preenchido_rr: int
    n_distintos_rr: int
    exemplos_rr: str

    @property
    def pct_preenchido_br(self) -> float:
        return round(100 * self.n_preenchido_br / self.n_linhas_br, 1) if self.n_linhas_br else 0.0

    @property
    def pct_preenchido_rr(self) -> float:
        return round(100 * self.n_preenchido_rr / self.n_linhas_rr, 1) if self.n_linhas_rr else 0.0


def classificar_bloco(coluna: str) -> str:
    for padrao, bloco in _REGRAS_BLOCO:
        if re.search(padrao, coluna):
            return bloco
    return "não classificado"


def _q(col: str) -> str:
    return '"' + col.replace('"', '""') + '"'


def catalogar_arquivo(ano: int, tabela: str, n_exemplos: int = 4) -> list[VariavelArquivo]:
    """Estatísticas de todas as colunas de um arquivo, via DuckDB, sem carregar
    o CSV em pandas. Campo vazio no CSV é lido como NULL (não preenchido)."""
    perfil = perfilar_csv(ano, tabela, contar_linhas=False)
    rotulo = str(ano) if tabela == "escola" else f"{ano}_{tabela}"
    enc = "latin-1" if perfil.encoding == "cp1252" else perfil.encoding
    fonte = (
        f"read_csv('{caminho(ano, tabela).as_posix()}', delim='{perfil.separador}', "
        f"header=true, encoding='{enc}', all_varchar=true)"
    )
    cols = perfil.colunas
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE t AS SELECT * FROM {fonte}")
        n_br = con.execute("SELECT count(*) FROM t").fetchone()[0]
        preenchido_br = con.execute(
            "SELECT " + ", ".join(f"count({_q(c)})" for c in cols) + " FROM t"
        ).fetchone()
        filtro_rr = "WHERE SG_UF = 'RR'" if "SG_UF" in cols else ""
        con.execute(f"CREATE TABLE rr AS SELECT * FROM t {filtro_rr}")
        n_rr = con.execute("SELECT count(*) FROM rr").fetchone()[0]
        preenchido_rr = con.execute(
            "SELECT " + ", ".join(f"count({_q(c)})" for c in cols) + " FROM rr"
        ).fetchone()
        distintos_rr = con.execute(
            "SELECT " + ", ".join(f"count(DISTINCT {_q(c)})" for c in cols) + " FROM rr"
        ).fetchone()
        itens = []
        for pos, c in enumerate(cols, start=1):
            exemplos = con.execute(
                f"SELECT {_q(c)} AS v, count(*) AS n FROM rr WHERE {_q(c)} IS NOT NULL "
                f"GROUP BY 1 ORDER BY n DESC, v LIMIT {n_exemplos}"
            ).fetchall()
            prefixo = c.split("_", 1)[0]
            itens.append(VariavelArquivo(
                rotulo, ano, tabela, pos, c, prefixo, PREFIXOS.get(prefixo, "outro"),
                classificar_bloco(c), n_br, preenchido_br[pos - 1], n_rr,
                preenchido_rr[pos - 1], distintos_rr[pos - 1],
                "; ".join(f"{v} ({n})" for v, n in exemplos),
            ))
    finally:
        con.close()
    return itens


def catalogar(destino_docs: pathlib.Path = DOCS) -> tuple[pathlib.Path, pathlib.Path]:
    todos: list[VariavelArquivo] = []
    for ano, tabela in sorted(ARQUIVOS):
        logger.info("Catalogando %s %s", ano, tabela)
        todos.extend(catalogar_arquivo(ano, tabela))

    destino_docs.mkdir(parents=True, exist_ok=True)
    longo = destino_docs / "catalogo_variaveis_microdados.csv"
    with longo.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "arquivo", "ano", "tabela", "posicao", "coluna", "prefixo", "tipo_semantico",
            "bloco", "n_linhas_br", "pct_preenchido_br", "n_linhas_rr", "pct_preenchido_rr",
            "n_distintos_rr", "exemplos_rr",
        ])
        for v in todos:
            w.writerow([
                v.rotulo, v.ano, v.tabela, v.posicao, v.coluna, v.prefixo, v.tipo_semantico,
                v.bloco, v.n_linhas_br, v.pct_preenchido_br, v.n_linhas_rr,
                v.pct_preenchido_rr, v.n_distintos_rr, v.exemplos_rr,
            ])

    rotulos = [str(a) if t == "escola" else f"{a}_{t}" for a, t in sorted(ARQUIVOS)]
    por_coluna: dict[str, dict[str, VariavelArquivo]] = {}
    for v in todos:
        por_coluna.setdefault(v.coluna, {})[v.rotulo] = v
    largo = destino_docs / "catalogo_variaveis.csv"
    with largo.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "coluna", "prefixo", "tipo_semantico", "bloco", "descricao", *rotulos, "n_arquivos",
            "arquivo_ref", "pct_preenchido_br_ref", "pct_preenchido_rr_ref",
            "n_distintos_rr_ref", "exemplos_rr_ref",
        ])
        def ordem(col: str) -> tuple:
            vs = por_coluna[col]
            primeiro = next(r for r in rotulos if r in vs)
            return (rotulos.index(primeiro), vs[primeiro].posicao)
        for col in sorted(por_coluna, key=ordem):
            vs = por_coluna[col]
            ref = vs[[r for r in rotulos if r in vs][-1]]
            w.writerow([
                col, ref.prefixo, ref.tipo_semantico, ref.bloco, "",
                *[vs[r].posicao if r in vs else "" for r in rotulos], len(vs),
                ref.rotulo, ref.pct_preenchido_br, ref.pct_preenchido_rr,
                ref.n_distintos_rr, ref.exemplos_rr,
            ])
    return longo, largo


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    longo, largo = catalogar()
    logger.info("Gravados %s e %s", longo, largo)
