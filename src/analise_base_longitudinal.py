"""Análise descritiva da base longitudinal v1.0 do orientador
(dados/externo/base_longitudinal_v1/base_longitudinal_abandono_rr_2019_2025.csv).

Gera em docs/ as tabelas citadas em docs/metodologia_variaveis.md:
- desfechos_distribuicao.csv   — por etapa × ano: n, média, mediana, p75, p90,
                                 máximo e % de zeros da taxa de abandono (públicas)
- desfechos_persistencia.csv   — por etapa × transição t→t+1: n, Spearman,
                                 MAE do baseline B1 (persistência) e do B0 (média)
- desfechos_cobertura.csv      — por ano: escolas públicas com AF, com EM, união e interseção
- ausencia_base_longitudinal.csv — % de ausência por variável (públicas)
- estrato_nome_indigena.csv    — proxy fraco: escolas com 'INDIGENA' no nome
                                 (a fonte correta é IN_EDUCACAO_INDIGENA do Censo, D8)

Não seleciona variável nem olha correlação preditor × desfecho (regra 3):
a única correlação calculada é a do desfecho com ele mesmo no ano anterior,
que define o baseline de persistência (B1) da proposta do orientador.
"""
from __future__ import annotations

import logging
import pathlib

import pandas as pd

from src.config import BASE_LONGITUDINAL_V1, DOCS

logger = logging.getLogger(__name__)

BASE_ORIENTADOR = BASE_LONGITUDINAL_V1 / "base_longitudinal_abandono_rr_2019_2025.csv"
DESFECHOS = {"AF": "ABANDONO_FUN_AF", "EM": "ABANDONO_MED"}


def carregar_base(caminho: pathlib.Path = BASE_ORIENTADOR) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Base do orientador não encontrada em {caminho}.\n"
            f"Ela é dado externo, entregue pelo orientador (dados/externo/base_longitudinal_v1/),\n"
            f"não é obtenível do INEP nem gerada por este projeto ainda; o sha256 esperado está\n"
            f"em dados/MANIFEST.csv (estagio=externo)."
        )
    return pd.read_csv(caminho, encoding="utf-8-sig", dtype={"CO_ENTIDADE": "string", "CO_MUNICIPIO": "string"})


def _spearman(x: pd.Series, y: pd.Series) -> float:
    # ranks + Pearson == Spearman; evita depender de scipy antes da modelagem
    return float(x.rank().corr(y.rank()))


def distribuicao(pub: pd.DataFrame) -> pd.DataFrame:
    partes = []
    for etapa, col in DESFECHOS.items():
        g = pub.dropna(subset=[col]).groupby("ANO")[col]
        d = pd.DataFrame({
            "n": g.count(), "media": g.mean().round(2), "mediana": g.median().round(2),
            "p75": g.quantile(0.75).round(1), "p90": g.quantile(0.9).round(1), "max": g.max(),
            "pct_zero": g.apply(lambda s: (s == 0).mean() * 100).round(1),
        })
        d.insert(0, "etapa", etapa)
        partes.append(d.reset_index())
    return pd.concat(partes, ignore_index=True)


def persistencia(pub: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for etapa, col in DESFECHOS.items():
        t1 = f"{col}_T1"
        for ano, s in pub.groupby("ANO"):
            x = s[[col, t1]].dropna()
            if len(x) < 10:
                continue
            linhas.append({
                "etapa": etapa, "transicao": f"{ano}->{ano + 1}", "n": len(x),
                "spearman_t_t1": round(_spearman(x[col], x[t1]), 2),
                "mae_b1_persistencia": round((x[col] - x[t1]).abs().mean(), 2),
                "mae_b0_media": round((x[t1] - x[t1].mean()).abs().mean(), 2),
                "pct_zero_t1": round((x[t1] == 0).mean() * 100, 1),
            })
    return pd.DataFrame(linhas)


def cobertura(pub: pd.DataFrame) -> pd.DataFrame:
    af, em = DESFECHOS["AF"], DESFECHOS["EM"]
    return pub.groupby("ANO").apply(lambda s: pd.Series({
        "publicas": len(s),
        "com_AF": s[af].notna().sum(), "com_EM": s[em].notna().sum(),
        "AF_ou_EM": (s[af].notna() | s[em].notna()).sum(),
        "AF_e_EM": (s[af].notna() & s[em].notna()).sum(),
        "com_alvo_AF_t1": s[f"{af}_T1"].notna().sum(), "com_alvo_EM_t1": s[f"{em}_T1"].notna().sum(),
    }), include_groups=False).reset_index()


def ausencia(pub: pd.DataFrame) -> pd.DataFrame:
    return pub.isna().mean().mul(100).round(1).rename("pct_ausente_publicas").rename_axis("variavel").reset_index()


def indigena_por_nome(pub: pd.DataFrame) -> pd.DataFrame:
    ind = pub["NO_ENTIDADE"].str.contains("INDIGENA|INDÍGENA", case=False, regex=True)
    linhas = []
    for rotulo, mask in (("indigena_nome", ind), ("nao_indigena_nome", ~ind)):
        s = pub[mask]
        linhas.append({
            "grupo": rotulo, "linhas": len(s), "escolas_distintas": s["CO_ENTIDADE"].nunique(),
            "n_AF": s[DESFECHOS["AF"]].notna().sum(), "media_AF": round(s[DESFECHOS["AF"]].mean(), 2),
            "n_EM": s[DESFECHOS["EM"]].notna().sum(), "media_EM": round(s[DESFECHOS["EM"]].mean(), 2),
        })
    return pd.DataFrame(linhas)


def gerar(destino: pathlib.Path = DOCS) -> list[pathlib.Path]:
    base = carregar_base()
    pub = base[base["REDE_PUBLICA"] == 1]
    saidas = {
        "desfechos_distribuicao.csv": distribuicao(pub),
        "desfechos_persistencia.csv": persistencia(pub),
        "desfechos_cobertura.csv": cobertura(pub),
        "ausencia_base_longitudinal.csv": ausencia(pub),
        "estrato_nome_indigena.csv": indigena_por_nome(pub),
    }
    gravados = []
    for nome, df in saidas.items():
        p = destino / nome
        df.to_csv(p, index=False, encoding="utf-8")
        logger.info("Gravado %s (%d linhas)", p, len(df))
        gravados.append(p)
    return gravados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    gerar()
