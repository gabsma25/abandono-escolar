"""Regera a base longitudinal escola-ano de RR a partir dos indicadores do INEP
(dados/interim/indicadores_rr/) e a compara com a v1.0 do orientador.

    python -m src.base_longitudinal

Saída: dados/processado/base_longitudinal_rr_2019_2025.parquet (+ .csv `;`)
e docs/comparacao_base_v1.csv (critério 2 do §8 do CLAUDE.md).

Etapas (plano aprovado em 2026-09-30; regras verificadas contra a v1.0):

1. Harmonização por fonte: cada planilha vira colunas com os nomes da v1.0.
   Em tx_rend 2019–2020 os nomes técnicos são outros (tap_/tre_/tab_) e o
   mapeamento é POSICIONAL, conferido contra o rótulo humano de cada posição
   em docs/presenca_colunas_indicadores.csv: `tap_F04` está sob "Anos Finais"
   e vira 1_CAT_FUN_AF — o nome técnico engana (P014).
2. Universo = união das chaves (ANO, CO_ENTIDADE) das fontes que o definem;
   um merge `how="left", validate="1:1"` por fonte, a partir dessa tabela.
   Identidade (nome, município, localização, dependência): primeiro valor não
   nulo na ordem das FONTES (tx_rend primeiro — é o que a v1.0 usa nas 6
   linhas de 2021+ em que o nome diverge entre fontes).
3. Derivadas da linha: REDE_PUBLICA, DISP_* (sobre as colunas mantidas da
   fonte), IED_*_ALTO = N4+N5+N6. Nenhuma estatística entre linhas é calculada
   aqui (média, quantil, imputação): não há o que ajustar no treino.
4. Derivadas temporais por junção explícita em ANO±1 na mesma escola — nunca
   shift(), que ligaria 2019 a 2021 se a escola faltasse em 2020. LAG1 e
   DELTA1 só leem t−1; ausente em qualquer ponta dá ausente (regra 5). *_T1
   só lê o próprio desfecho em t+1 e nenhuma outra coluna deriva dele.
5. Validações do validacao_base_longitudinal.json por `assert`.

Extensão D8 (não incluída): as colunas do Censo entram como mais uma Fonte,
com define_universo=False — nada mais muda.
"""
from __future__ import annotations

import csv
import logging
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import BASE_LONGITUDINAL_V1, DOCS, PROCESSADO
from src.indicadores_rr import caminho_rr
from src.integridade import sha256_arquivo

logger = logging.getLogger(__name__)

ANOS = range(2019, 2026)
SAIDA = PROCESSADO / "base_longitudinal_rr_2019_2025.parquet"
BASE_V1 = BASE_LONGITUDINAL_V1 / "base_longitudinal_abandono_rr_2019_2025.csv"
COMPARACAO = DOCS / "comparacao_base_v1.csv"
PRESENCA = DOCS / "presenca_colunas_indicadores.csv"

CHAVE = ["ANO", "CO_ENTIDADE"]
IDENTIDADE = ["NO_ENTIDADE", "CO_MUNICIPIO", "NO_MUNICIPIO", "LOCALIZACAO", "DEPENDENCIA"]
# Nomes de identidade nas planilhas 2021+ e em TDI/ATU/IED (todos os anos).
_ID_TECNICO = {"NU_ANO_CENSO": "ANO", "NO_CATEGORIA": "LOCALIZACAO", "NO_DEPENDENCIA": "DEPENDENCIA"}


def _por_etapa(prefixo: str, nome: str) -> dict[str, str]:
    return {f"{prefixo}_CAT_FUN": f"{nome}_FUN", f"{prefixo}_CAT_FUN_AI": f"{nome}_FUN_AI",
            f"{prefixo}_CAT_FUN_AF": f"{nome}_FUN_AF", f"{prefixo}_CAT_MED": f"{nome}_MED"}


# Coluna técnica (geração 2021+) → nome na base. Nomes verificados em
# docs/presenca_colunas_indicadores.csv e no dicionário da v1.0.
MAPA_TX_REND = {**_por_etapa("1", "APROVACAO"), **_por_etapa("2", "REPROVACAO"), **_por_etapa("3", "ABANDONO")}
MAPA_TDI = {"FUN_CAT_0": "TDI_FUN_TOTAL", "FUN_AI_CAT_0": "TDI_FUN_AI",
            "FUN_AF_CAT_0": "TDI_FUN_AF", "MED_CAT_0": "TDI_MED_TOTAL"}
MAPA_ATU = {"FUN_CAT_0": "ATU_FUN_TOTAL", "FUN_AI_CAT_0": "ATU_FUN_AI",
            "FUN_AF_CAT_0": "ATU_FUN_AF", "MED_CAT_0": "ATU_MED_TOTAL"}
MAPA_IED = {f"{e}_CAT_{n}": f"IED_{e}_N{n}" for e in ("FUN", "MED") for n in range(1, 7)}


def mapa_posicional_tx_rend(presenca: pathlib.Path = PRESENCA) -> dict[str, str]:
    """{coluna 2019–2020: coluna 2021+} por posição na planilha de escolas.

    Para cada posição, o rótulo humano das duas gerações precisa ser o mesmo;
    senão é erro — é a trava contra a armadilha F04/F58 (P014) e contra uma
    reordenação futura das planilhas.
    """
    p = pd.read_csv(presenca, dtype=str)
    t = p[(p["tipo"] == "tx_rend") & (p["nivel"] == "escolas")]
    geracoes = {}
    for ano in ("2019", "2020", "2021"):
        g = t[t[ano].notna()].assign(pos=lambda d, a=ano: d[a].astype(int)).set_index("pos").sort_index()
        geracoes[ano] = g
    assert list(geracoes["2019"]["coluna"]) == list(geracoes["2020"]["coluna"]), \
        "tx_rend 2019 e 2020 não têm as mesmas colunas nas mesmas posições"
    antigo, novo = geracoes["2019"], geracoes["2021"]
    assert list(antigo.index) == list(novo.index), "tx_rend: número/posições de colunas diferem entre gerações"
    divergentes = antigo.index[antigo["descricao"] != novo["descricao"]]
    assert divergentes.empty, (
        "tx_rend: rótulo humano difere na mesma posição entre 2019 e 2021 — o mapeamento posicional "
        f"não vale: {antigo.loc[divergentes, ['coluna', 'descricao']].to_dict('records')}"
    )
    return dict(zip(antigo["coluna"], novo["coluna"], strict=True))


@dataclass(frozen=True)
class Fonte:
    nome: str
    tipo_disp: str | None                   # sufixo da coluna DISP_*; None = sem DISP
    anos: range
    carregar: Callable[[int], pd.DataFrame]   # ano → colunas CHAVE + IDENTIDADE + valores
    colunas: tuple[str, ...]                  # colunas de valor que a fonte traz para a base
    define_universo: bool = True


def _carregar_indicador(tipo: str, mapa: dict[str, str], renomear_geracao: dict[str, str] | None = None
                        ) -> Callable[[int], pd.DataFrame]:
    def carregar(ano: int) -> pd.DataFrame:
        df = pd.read_parquet(caminho_rr(tipo, ano))
        if renomear_geracao and ano <= 2020:
            assert list(df.columns) == list(renomear_geracao), f"{tipo} {ano}: colunas fora da ordem esperada"
            df = df.rename(columns=renomear_geracao)
        df = df.rename(columns={**_ID_TECNICO, **mapa})
        assert (df["ANO"] == ano).all(), f"{tipo} {ano}: coluna de ano com outro valor"
        assert df["CO_ENTIDADE"].is_unique, f"{tipo} {ano}: CO_ENTIDADE repetido"
        return df[CHAVE + IDENTIDADE + list(mapa.values())]
    return carregar


def fontes() -> list[Fonte]:
    """Fontes na ordem de prioridade da identidade. D8 entraria aqui."""
    return [
        Fonte("tx_rend", "REND", ANOS, _carregar_indicador("tx_rend", MAPA_TX_REND, mapa_posicional_tx_rend()),
              tuple(MAPA_TX_REND.values())),
        Fonte("TDI", "TDI", ANOS, _carregar_indicador("TDI", MAPA_TDI), tuple(MAPA_TDI.values())),
        Fonte("ATU", "ATU", ANOS, _carregar_indicador("ATU", MAPA_ATU), tuple(MAPA_ATU.values())),
        # IED escola 2019–2020 existe desde P019, mas o desenho segue 2021+ até decisão.
        Fonte("IED", "IED", range(2021, 2026), _carregar_indicador("IED", MAPA_IED), tuple(MAPA_IED.values())),
    ]


# Ordem e nomes das colunas da v1.0 (dicionario_base_longitudinal.csv).
COLUNAS = [
    "ANO", "ANO_ALVO", "CO_ENTIDADE", "NO_ENTIDADE", "CO_MUNICIPIO", "NO_MUNICIPIO", "LOCALIZACAO",
    "DEPENDENCIA", "REDE_PUBLICA", "DISP_ATU", "DISP_TDI", "DISP_IED", "DISP_REND",
    *MAPA_ATU.values(), *MAPA_TDI.values(),
    *[f"IED_FUN_N{n}" for n in range(1, 7)], "IED_FUN_ALTO",
    *[f"IED_MED_N{n}" for n in range(1, 7)], "IED_MED_ALTO",
    *MAPA_TX_REND.values(),
    "ABANDONO_FUN_LAG1", "ABANDONO_FUN_AF_LAG1", "ABANDONO_MED_LAG1",
    "TDI_FUN_AF_DELTA1", "TDI_MED_TOTAL_DELTA1", "ATU_FUN_AF_DELTA1", "ATU_MED_TOTAL_DELTA1",
    "ABANDONO_FUN_AF_DELTA1", "ABANDONO_MED_DELTA1",
    "ABANDONO_FUN_T1", "ABANDONO_FUN_AF_T1", "ABANDONO_MED_T1",
]
LAG1 = ["ABANDONO_FUN", "ABANDONO_FUN_AF", "ABANDONO_MED"]
DELTA1 = ["TDI_FUN_AF", "TDI_MED_TOTAL", "ATU_FUN_AF", "ATU_MED_TOTAL", "ABANDONO_FUN_AF", "ABANDONO_MED"]
T1 = ["ABANDONO_FUN", "ABANDONO_FUN_AF", "ABANDONO_MED"]


# Tolerância ABSOLUTA, e não relativa: todo valor comparado é taxa, percentual
# ou média de alunos numa escala limitada (0–100, dezenas), e o erro a absorver
# é o de ponto flutuante da aritmética (≈1e-14 nessa escala). Relativa seria
# frouxa demais perto de 100 e rígida demais perto de 0.
TOLERANCIA = 1e-9
# Colunas que passaram por aritmética (aqui ou no script do orientador):
# diferença até TOLERANCIA é "idêntica na tolerância". Nas demais, cópias das
# planilhas do INEP, qualquer diferença de valor é divergência.
ARITMETICA = {"IED_FUN_ALTO", "IED_MED_ALTO", *(f"{x}_DELTA1" for x in DELTA1)}



def unir(fontes_: list[Fonte]) -> pd.DataFrame:
    """Tabela de chaves (união das fontes que definem o universo) + um merge
    left 1:1 por fonte; identidade = primeiro não nulo na ordem das fontes."""
    por_fonte = {f.nome: pd.concat([f.carregar(a) for a in f.anos], ignore_index=True) for f in fontes_}
    chaves = (pd.concat([por_fonte[f.nome][CHAVE] for f in fontes_ if f.define_universo])
              .drop_duplicates().sort_values(CHAVE).reset_index(drop=True))
    base = chaves
    for f in fontes_:
        df = por_fonte[f.nome].rename(columns={c: f"{c}__{f.nome}" for c in IDENTIDADE})
        base = base.merge(df, on=CHAVE, how="left", validate="1:1")
    for col in IDENTIDADE:
        candidatos = [f"{col}__{f.nome}" for f in fontes_]
        valores = base[candidatos]
        base[col] = valores.bfill(axis=1).iloc[:, 0].astype("string")
        divergem = int((valores.nunique(axis=1) > 1).sum())
        if divergem:
            logger.info("%s difere entre fontes em %d linha(s); usada a de maior prioridade (%s).",
                        col, divergem, fontes_[0].nome)
        base = base.drop(columns=candidatos)
    return base


def derivar(base: pd.DataFrame, fontes_: list[Fonte]) -> pd.DataFrame:
    base = base.copy()
    base["REDE_PUBLICA"] = (base["DEPENDENCIA"] != "Privada").astype("Int8")
    for f in fontes_:
        if f.tipo_disp:
            base[f"DISP_{f.tipo_disp}"] = base[list(f.colunas)].notna().any(axis=1).astype("Int8")
    for etapa in ("FUN", "MED"):
        base[f"IED_{etapa}_ALTO"] = base[f"IED_{etapa}_N4"] + base[f"IED_{etapa}_N5"] + base[f"IED_{etapa}_N6"]

    def no_ano(delta: int, cols: list[str], sufixo: str) -> pd.DataFrame:
        """Valores da mesma escola em ANO+delta, alinhados à linha de ANO."""
        outro = base[CHAVE + cols].assign(ANO=lambda d: d["ANO"] - delta)
        outro = outro.rename(columns={c: f"{c}{sufixo}" for c in cols})
        return base[CHAVE].merge(outro, on=CHAVE, how="left", validate="1:1")

    anterior = no_ano(-1, sorted(set(LAG1) | set(DELTA1)), "__t-1")
    seguinte = no_ano(+1, T1, "__t+1")
    for x in LAG1:
        base[f"{x}_LAG1"] = anterior[f"{x}__t-1"].to_numpy()
    for x in DELTA1:
        base[f"{x}_DELTA1"] = base[x] - pd.array(anterior[f"{x}__t-1"], dtype="Float64")
    for x in T1:
        base[f"{x}_T1"] = seguinte[f"{x}__t+1"].to_numpy()
    existe = base[CHAVE].assign(ANO=lambda d: d["ANO"] - 1, _existe=True)
    tem_seguinte = base[CHAVE].merge(existe, on=CHAVE, how="left", validate="1:1")["_existe"].notna()
    base["ANO_ALVO"] = pd.array(np.where(tem_seguinte, base["ANO"] + 1, pd.NA), dtype="Int16")
    return _tipar(base[COLUNAS])


def _tipar(base: pd.DataFrame) -> pd.DataFrame:
    tipos = {}
    for c in base.columns:
        if c in ("ANO", "ANO_ALVO"):
            tipos[c] = "Int16"
        elif c == "REDE_PUBLICA" or c.startswith("DISP_"):
            tipos[c] = "Int8"
        elif c in ("CO_ENTIDADE",) or c in IDENTIDADE:
            tipos[c] = "string"
        else:
            tipos[c] = "Float64"
    return base.astype(tipos).sort_values(CHAVE).reset_index(drop=True)


def _tol(coluna: str) -> float:
    return TOLERANCIA if coluna in ARITMETICA else 0.0


def validar(base: pd.DataFrame) -> dict:
    """Validações do validacao_base_longitudinal.json, por assert (critério 3)."""
    assert not base.duplicated(CHAVE).any(), "chave ANO + CO_ENTIDADE repetida"
    taxas = [c for c in base.columns if c.split("_")[0] in ("APROVACAO", "REPROVACAO", "ABANDONO", "TDI", "IED")
             and not c.endswith("_DELTA1")]
    # Colunas calculadas por soma podem passar de 100 por ruído de ponto
    # flutuante (76,9 + 15,4 + 7,7 = 100.00000000000001): mesma TOLERANCIA
    # da comparação. Colunas copiadas das planilhas: limite exato.
    fora = {c: int(((base[c] < -_tol(c)) | (base[c] > 100 + _tol(c))).sum()) for c in taxas}
    assert not any(fora.values()), f"taxas fora de [0, 100]: { {k: v for k, v in fora.items() if v} }"
    atu = {c: int((base[c] <= 0).sum()) for c in MAPA_ATU.values()}
    assert not any(atu.values()), f"ATU não positivo: {atu}"
    for sufixo in ("FUN", "FUN_AI", "FUN_AF", "MED"):
        soma = base[f"APROVACAO_{sufixo}"] + base[f"REPROVACAO_{sufixo}"] + base[f"ABANDONO_{sufixo}"]
        assert ((soma - 100).abs().dropna() <= 0.2).all(), f"aprovação+reprovação+abandono ≠ 100 em {sufixo}"
    for etapa in ("FUN", "MED"):
        soma = sum(base[f"IED_{etapa}_N{n}"] for n in range(1, 7))
        assert ((soma - 100).abs().dropna() <= 0.2).all(), f"Σ IED ≠ 100 em {etapa}"
    por_escola = base.groupby("CO_ENTIDADE")
    mudancas = {c: int((por_escola[c].nunique() > 1).sum()) for c in IDENTIDADE}
    assert mudancas["CO_MUNICIPIO"] == 0, "escola muda de município"
    assert mudancas["DEPENDENCIA"] == 0, "escola muda de dependência"
    logger.info("Validações passaram: %d linhas; escolas que mudam de localização: %d, de nome: %d.",
                len(base), mudancas["LOCALIZACAO"], mudancas["NO_ENTIDADE"])
    return {"linhas": len(base), "mudam_localizacao": mudancas["LOCALIZACAO"], "mudam_nome": mudancas["NO_ENTIDADE"]}


def gerar(saida: pathlib.Path = SAIDA) -> pd.DataFrame:
    fs = fontes()
    base = derivar(unir(fs), fs)
    validar(base)
    saida.parent.mkdir(parents=True, exist_ok=True)
    base.to_parquet(saida, index=False)
    base.to_csv(saida.with_suffix(".csv"), sep=";", index=False)
    logger.info("Gravado %s (%d linhas × %d colunas)", saida, *base.shape)
    return base


# ── Comparação com a v1.0 (critério 2) ─────────────────────────────────────

def _ler_v1(caminho: pathlib.Path) -> pd.DataFrame:
    v1 = pd.read_csv(caminho, encoding="utf-8-sig",
                     dtype={"CO_ENTIDADE": "string", "CO_MUNICIPIO": "string"})
    return _tipar(v1)


def comparar(nova: pd.DataFrame, v1_caminho: pathlib.Path = BASE_V1,
             destino: pathlib.Path = COMPARACAO) -> pd.DataFrame:
    """Compara coluna a coluna com a v1.0; a ausência é comparada ANTES dos
    valores (NaN != NaN tornaria idêntica uma coluna vazia divergente e
    vice-versa). Grava docs/comparacao_base_v1.csv."""
    v1 = _ler_v1(v1_caminho)
    sha_v1 = sha256_arquivo(v1_caminho)
    linhas = []
    so_nova = nova.merge(v1[CHAVE], on=CHAVE, how="left", indicator=True, validate="1:1")
    so_v1 = v1[CHAVE].merge(nova[CHAVE], on=CHAVE, how="left", indicator=True, validate="1:1")
    n_so_nova, n_so_v1 = int((so_nova["_merge"] == "left_only").sum()), int((so_v1["_merge"] == "left_only").sum())
    linhas.append({"coluna": "(chave ANO+CO_ENTIDADE)", "n_comparadas": len(nova) - n_so_nova,
                   "ausente_so_nova": n_so_v1, "ausente_so_v1": n_so_nova, "n_valores_diferentes": 0,
                   "n_dentro_tolerancia": 0, "max_diferenca_abs": 0.0,
                   "classificacao": "idêntica" if not (n_so_nova or n_so_v1) else "universo diverge"})
    a = nova.merge(v1, on=CHAVE, how="inner", suffixes=("", "__v1"), validate="1:1")
    for col in COLUNAS:
        if col in CHAVE:
            continue
        if col not in v1.columns:
            linhas.append({"coluna": col, "classificacao": "ausente na v1"})
            continue
        x, y = a[col], a[f"{col}__v1"]
        na_x, na_y = x.isna().to_numpy(), y.isna().to_numpy()
        ambos = ~na_x & ~na_y
        if pd.api.types.is_numeric_dtype(x):
            dif = np.abs(x.to_numpy(dtype="float64", na_value=np.nan)[ambos]
                         - y.to_numpy(dtype="float64", na_value=np.nan)[ambos])
            n_dif, n_tol = int((dif > 0).sum()), int(((dif > 0) & (dif <= TOLERANCIA)).sum())
            max_dif = float(dif.max()) if dif.size else 0.0
        else:
            n_dif = int((x.to_numpy()[ambos] != y.to_numpy()[ambos]).sum())
            n_tol, max_dif = 0, float("nan")
        classes = []
        if (na_x != na_y).any():
            classes.append("ausência diverge")
        if n_dif and (col not in ARITMETICA or n_dif > n_tol):
            classes.append("valor diverge")
        elif n_dif:
            classes.append("idêntica na tolerância")
        linhas.append({
            "coluna": col, "n_comparadas": len(a),
            "ausente_so_nova": int((na_x & ~na_y).sum()), "ausente_so_v1": int((~na_x & na_y).sum()),
            "n_valores_diferentes": n_dif, "n_dentro_tolerancia": n_tol, "max_diferenca_abs": max_dif,
            "classificacao": " + ".join(classes) or "idêntica",
        })
    extras = sorted(set(v1.columns) - set(COLUNAS))
    for col in extras:
        linhas.append({"coluna": col, "classificacao": "ausente na base regerada"})
    res = pd.DataFrame(linhas)
    res.insert(0, "v1_sha256", sha_v1)
    res["tolerancia_abs"] = [_tol(c) for c in res["coluna"]]
    destino.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(destino, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    resumo = res["classificacao"].value_counts().to_dict()
    logger.info("Comparação com a v1.0 (sha256 %s…): %s. Gravado %s", sha_v1[:12], resumo, destino)
    return res


def main() -> None:
    base = gerar()
    if BASE_V1.exists():
        res = comparar(base)
        divergentes = res[~res["classificacao"].isin(["idêntica", "idêntica na tolerância"])]
        for r in divergentes.itertuples():
            logger.warning("Diferença com a v1.0 em %s: %s", r.coluna, r.classificacao)
    else:
        logger.warning("Base v1.0 ausente em %s; comparação (critério 2) não feita.", BASE_V1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
