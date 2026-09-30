"""Fixtures comuns. Nenhum teste lê dados/ de verdade nem faz requisição de rede:
zips são sintéticos, em pasta temporária, e o destino de arquivos divergentes
é redirecionado para ela."""
from __future__ import annotations

import hashlib
import pathlib
import zipfile

import pytest

import src.integridade


def md5(conteudo: bytes) -> str:
    return hashlib.md5(conteudo).hexdigest()


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def criar_zip(caminho: pathlib.Path, membros: dict[str, bytes]) -> pathlib.Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho, "w") as zf:
        for nome, conteudo in membros.items():
            zf.writestr(nome, conteudo)
    return caminho


@pytest.fixture(autouse=True)
def divergente_temporario(tmp_path, monkeypatch) -> pathlib.Path:
    """Arquivos que não conferem vão para tmp, nunca para dados/cache_download/."""
    pasta = tmp_path / "divergente"
    monkeypatch.setattr(src.integridade, "DIVERGENTE", pasta)
    return pasta


@pytest.fixture
def zip_indicador(tmp_path) -> dict:
    """Zip no layout do INEP: pasta interna, .xlsx, .ods, md5_*.txt e lixo."""
    xlsx, ods = b"planilha xlsx de teste", b"planilha ods de teste"
    txt = f"{md5(xlsx)} *ATU_ESCOLAS_2019.xlsx\n{md5(ods)} *ATU_ESCOLAS_2019.ods\n".encode()
    origem = tmp_path / "origem"
    criar_zip(origem / "ATU_2019_ESCOLAS.zip", {
        "ATU_2019_ESCOLAS/ATU_ESCOLAS_2019.xlsx": xlsx,
        "ATU_2019_ESCOLAS/ATU_ESCOLAS_2019.ods": ods,
        "ATU_2019_ESCOLAS/md5_ATU_ESCOLAS_2019.txt": txt,
        "ATU_2019_ESCOLAS/Thumbs.db": b"lixo",
    })
    return {"origem": origem, "destino": tmp_path / "bruto", "xlsx": xlsx, "txt": txt}
