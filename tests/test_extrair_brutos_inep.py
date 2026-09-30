"""Regra 1 (CLAUDE.md §3) aplicada ao extrator de indicadores."""
from __future__ import annotations

import logging
import os
import pathlib

import pytest

from src.extrair_brutos_inep import escrever_extracao, extrair
from src.integridade import ErroIntegridade
from tests.conftest import criar_zip, md5, sha256


def _mtimes(pasta: pathlib.Path) -> dict[pathlib.Path, int]:
    return {p: p.stat().st_mtime_ns for p in pasta.rglob("*") if p.is_file()}


def _rodar(z: dict, **kw) -> list:
    itens = extrair(z["origem"], z["destino"], hashes=kw.pop("hashes", {}), **kw)
    escrever_extracao(itens, z["destino"].parent / "extracao.csv", raiz=z["destino"].parent)
    return itens


def test_extrai_so_xlsx_e_md5(zip_indicador):
    _rodar(zip_indicador)
    pasta = zip_indicador["destino"] / "ATU" / "2019"
    assert sorted(p.name for p in pasta.iterdir()) == [
        "ATU_ESCOLAS_2019.xlsx", "md5_ATU_ESCOLAS_2019.txt",
    ]
    assert (pasta / "ATU_ESCOLAS_2019.xlsx").read_bytes() == zip_indicador["xlsx"]
    assert not list(zip_indicador["destino"].rglob("*.parcial"))


def test_rodar_duas_vezes_nao_altera_mtime(zip_indicador):
    _rodar(zip_indicador)
    # Recua o mtime de tudo: se a 2ª execução regravar qualquer arquivo,
    # o mtime volta a ser "agora" e o teste pega, mesmo em relógio grosso.
    for p in zip_indicador["destino"].rglob("*"):
        if p.is_file():
            os.utime(p, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    antes = _mtimes(zip_indicador["destino"])

    _rodar(zip_indicador)

    assert _mtimes(zip_indicador["destino"]) == antes


def test_existente_divergente_e_erro_e_nao_e_regravado(zip_indicador):
    _rodar(zip_indicador)
    alvo = zip_indicador["destino"] / "ATU" / "2019" / "ATU_ESCOLAS_2019.xlsx"
    alvo.write_bytes(b"adulterado")

    with pytest.raises(ErroIntegridade, match="não será regravado"):
        _rodar(zip_indicador)
    assert alvo.read_bytes() == b"adulterado"


def test_sobrescrever_regrava_o_divergente(zip_indicador):
    _rodar(zip_indicador)
    alvo = zip_indicador["destino"] / "ATU" / "2019" / "ATU_ESCOLAS_2019.xlsx"
    alvo.write_bytes(b"adulterado")

    _rodar(zip_indicador, sobrescrever=True)

    assert alvo.read_bytes() == zip_indicador["xlsx"]


def test_md5_do_inep_divergente_vai_para_divergente(tmp_path, divergente_temporario):
    xlsx = b"conteudo real"
    criar_zip(tmp_path / "origem" / "TDI_2021_ESCOLAS.zip", {
        "TDI_2021_ESCOLAS/TDI_ESCOLAS_2021.xlsx": xlsx,
        "TDI_2021_ESCOLAS/md5_TDI_ESCOLAS_2021.txt": f"{'0' * 32} *TDI_ESCOLAS_2021.xlsx\n".encode(),
    })
    with pytest.raises(ErroIntegridade, match="md5 esperado"):
        extrair(tmp_path / "origem", tmp_path / "bruto", hashes={})
    assert not (tmp_path / "bruto" / "TDI" / "2021" / "TDI_ESCOLAS_2021.xlsx").exists()
    assert [p.read_bytes() for p in divergente_temporario.iterdir()] == [xlsx]


def test_manifesto_confere_e_md5_do_inep_desatualizado_e_so_aviso(tmp_path, caplog):
    """Caso P007/P020: o INEP publicou md5 velho; o manifesto do projeto manda."""
    xlsx = b"planilha regerada depois do md5"
    criar_zip(tmp_path / "origem" / "ATU_2022_ESCOLAS.zip", {
        "ATU_2022_ESCOLAS/ATU_ESCOLAS_2022.xlsx": xlsx,
        "ATU_2022_ESCOLAS/md5_ATU_ESCOLAS_2022.txt": f"{'f' * 32} *ATU_ESCOLAS_2022.xlsx\n".encode(),
    })
    caplog.set_level(logging.INFO)
    itens = extrair(tmp_path / "origem", tmp_path / "bruto",
                    hashes={"ATU_ESCOLAS_2022.xlsx": sha256(xlsx)})
    assert (tmp_path / "bruto" / "ATU" / "2022" / "ATU_ESCOLAS_2022.xlsx").read_bytes() == xlsx
    assert [i.md5_confere for i in itens if i.membro.endswith(".xlsx")] == [False]
    # Caso conhecido (P007): entra no resumo, sem WARNING por arquivo.
    assert "caso(s) conhecido(s)" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_setima_divergencia_de_md5_aparece_como_nova(tmp_path, caplog):
    """Divergência fora de MD5_INEP_DESATUALIZADO não se dilui no resumo."""
    xlsx = b"planilha"
    criar_zip(tmp_path / "origem" / "TDI_2023_ESCOLAS.zip", {
        "TDI_2023_ESCOLAS/TDI_ESCOLAS_2023.xlsx": xlsx,
        "TDI_2023_ESCOLAS/md5_TDI_ESCOLAS_2023.txt": f"{'e' * 32} *TDI_ESCOLAS_2023.xlsx\n".encode(),
    })
    extrair(tmp_path / "origem", tmp_path / "bruto", hashes={"TDI_ESCOLAS_2023.xlsx": sha256(xlsx)})
    novas = [r.getMessage() for r in caplog.records
             if r.levelno == logging.WARNING and "NOVA divergência" in r.getMessage()]
    assert len(novas) == 2   # um aviso na gravação e um no resumo final
    assert all("TDI_ESCOLAS_2023.xlsx" in m or "md5 do INEP" in m for m in novas)


def test_caso_conhecido_que_deixa_de_divergir_e_avisado(tmp_path, caplog):
    """Se o INEP corrigir o md5, o registro de casos conhecidos fica velho."""
    xlsx = b"planilha corrigida"
    criar_zip(tmp_path / "origem" / "HAD_2020_ESCOLAS.zip", {
        "HAD_2020_ESCOLAS/HAD_ESCOLAS_2020.xlsx": xlsx,
        "HAD_2020_ESCOLAS/md5_HAD_ESCOLAS_2020.txt": f"{md5(xlsx)} *HAD_ESCOLAS_2020.xlsx\n".encode(),
    })
    extrair(tmp_path / "origem", tmp_path / "bruto", hashes={})
    assert "deixou de divergir" in caplog.text


def test_manifesto_divergente_e_erro(tmp_path):
    criar_zip(tmp_path / "origem" / "ATU_2022_ESCOLAS.zip", {
        "ATU_2022_ESCOLAS/ATU_ESCOLAS_2022.xlsx": b"versao nova do INEP",
    })
    with pytest.raises(ErroIntegridade, match="sha256 esperado"):
        extrair(tmp_path / "origem", tmp_path / "bruto",
                hashes={"ATU_ESCOLAS_2022.xlsx": sha256(b"versao do manifesto")})


def test_md5_txt_com_caixa_e_nome_diferentes(tmp_path):
    """HAD municípios grafa '.xlsX'; tx_rend_escolas_2023 chama o md5 de '<nome>.txt'."""
    xlsx = b"had"
    criar_zip(tmp_path / "origem" / "HAD_2019_MUNICIPIOS.zip", {
        "HAD_2019_MUNICIPIOS/HAD_MUNICIPIOS_2019.xlsx": xlsx,
        "HAD_2019_MUNICIPIOS/HAD_MUNICIPIOS_2019.txt": f"{md5(xlsx)} *HAD_MUNICIPIOS_2019.xlsX\n".encode(),
    })
    itens = extrair(tmp_path / "origem", tmp_path / "bruto", hashes={})
    assert [i.md5_confere for i in itens if i.membro.endswith(".xlsx")] == [True]
