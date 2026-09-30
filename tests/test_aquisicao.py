"""Extração dos microdados do Censo: sha256 contra o manifesto e idempotência."""
from __future__ import annotations

import os

import pytest

from src.aquisicao import extrair_membro
from src.integridade import ErroIntegridade, hashes_manifesto
from tests.conftest import criar_zip, md5, sha256

CSV = b"NU_ANO_CENSO;SG_UF;CO_ENTIDADE\n2020;RR;14000001\n"


@pytest.fixture
def zip_censo(tmp_path):
    """Layout de 2020: pasta interna com acento corrompido (cp437), membro
    '.CSV' maiúsculo e md5_*.txt grafando '.csv' minúsculo."""
    return criar_zip(tmp_path / "microdados_censo_escolar_2020.zip", {
        "microdados_ed_basica_2020/Anexos/ANEXO I - Dicionário/dic.xlsx": b"x",
        "microdados_ed_basica_2020/dados/microdados_ed_basica_2020.CSV": CSV,
        "microdados_ed_basica_2020/dados/md5_microdados_ed_basica_2020.txt":
            f"{md5(CSV)} *microdados_ed_basica_2020.csv\n".encode(),
    })


def test_extrai_pelo_nome_base_preservando_a_caixa(zip_censo, tmp_path):
    destino = tmp_path / "bruto" / "microdados_ed_basica_2020.CSV"
    assert extrair_membro(zip_censo, destino.name, destino, sha256(CSV)) == "extraido"
    assert destino.read_bytes() == CSV
    assert [p.name for p in destino.parent.iterdir()] == ["microdados_ed_basica_2020.CSV"]


def test_segunda_extracao_nao_toca_o_arquivo(zip_censo, tmp_path):
    destino = tmp_path / "bruto" / "microdados_ed_basica_2020.CSV"
    extrair_membro(zip_censo, destino.name, destino, sha256(CSV))
    os.utime(destino, ns=(10**18, 10**18))

    assert extrair_membro(zip_censo, destino.name, destino, sha256(CSV)) == "ja_presente"
    assert destino.stat().st_mtime_ns == 10**18


def test_confere_existente_sem_precisar_do_zip(zip_censo, tmp_path):
    destino = tmp_path / "bruto" / "microdados_ed_basica_2020.CSV"
    extrair_membro(zip_censo, destino.name, destino, sha256(CSV))
    zip_censo.unlink()
    assert extrair_membro(zip_censo, destino.name, destino, sha256(CSV)) == "ja_presente"


def test_sha256_divergente_informa_arquivo_e_hashes(zip_censo, tmp_path, divergente_temporario):
    destino = tmp_path / "bruto" / "microdados_ed_basica_2020.CSV"
    esperado = "a" * 64
    with pytest.raises(ErroIntegridade) as erro:
        extrair_membro(zip_censo, destino.name, destino, esperado)
    msg = str(erro.value)
    assert "microdados_ed_basica_2020.CSV" in msg
    assert esperado in msg and sha256(CSV) in msg
    assert not destino.exists()
    assert len(list(divergente_temporario.iterdir())) == 1


def test_membro_ausente_lista_o_que_existe(zip_censo, tmp_path):
    with pytest.raises(ErroIntegridade, match="dic.xlsx"):
        extrair_membro(zip_censo, "Tabela_Escola_2020.csv", tmp_path / "x.csv", "a" * 64)


def test_manifesto_com_nome_repetido_e_hash_diferente_e_erro(tmp_path):
    m = tmp_path / "MANIFEST.csv"
    m.write_text(
        "estagio,origem,ano,tabela,arquivo,sha256,data_download\n"
        f"bruto,inep,2020,escola,bruto/censo/a.csv,{'1' * 64},2026-09-15\n"
        f"origem,inep,2020,escola,origem/a.csv,{'2' * 64},2026-09-15\n",
        encoding="utf-8",
    )
    with pytest.raises(ErroIntegridade, match="dois sha256"):
        hashes_manifesto(m)
