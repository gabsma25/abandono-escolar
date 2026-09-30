"""Aquisição dos dados do INEP: zips em dados/origem/ → arquivos em dados/bruto/.

Único módulo autorizado a criar arquivo em dados/origem/ e dados/bruto/
(CLAUDE.md §3, regra 1), e só o que não existe: arquivo presente e íntegro é
pulado; arquivo presente e divergente é erro, nunca sobrescrito.

Camada de extração (esta versão). Dos zips de microdados sai só o que o
projeto usa, com o nome exato do INEP (inclusive o `.CSV` maiúsculo de 2020):
o arquivo de escolas de cada ano e, em 2025, também Turma, Matrícula e
Docente. Cada arquivo é conferido duas vezes: contra o md5_*.txt do próprio
INEP dentro do zip e contra o sha256 de dados/MANIFEST.csv. Grava-se primeiro
em `<nome>.parcial` e só se renomeia para o nome final depois das duas
conferências — um arquivo com o nome final em bruto/ está sempre íntegro.

Fatos dos zips que o código trata (verificados em 2026-09-29):
- a pasta interna muda a cada ano ("microdados_ed_basica_2019/",
  "Microdados do Censo Escolar da Educação Básica 2022/",
  "microdados_censo_escolar_2024_defeso/"...), e até 2023 o nome vem em cp437
  com acento corrompido — o membro é localizado pelo nome-base, nunca pelo
  caminho;
- o md5_*.txt do INEP diverge na caixa do nome (".csv" para o membro ".CSV"
  em 2020, "_v2.csv" para "_V2.csv" em 2025) — a comparação ignora caixa.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import pathlib
import zipfile

from src.config import ARQUIVOS, MANIFEST, ORIGEM_CENSO, ORIGEM_DOC
from src.extrair_brutos_inep import _ler_md5_txt

logger = logging.getLogger(__name__)

# Nome do zip de microdados de cada ano, como publicado pelo INEP. 2025 tem o
# underscore extra no fim. Fallback estático da descoberta (etapa seguinte).
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

_SUFIXO_PARCIAL = ".parcial"


class ErroIntegridade(RuntimeError):
    """Hash divergente, membro ausente ou arquivo existente que não confere."""


def sha256_arquivo(caminho: pathlib.Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def hashes_manifesto(caminho: pathlib.Path = MANIFEST) -> dict[str, str]:
    """{nome-base do arquivo: sha256} de dados/MANIFEST.csv.

    Chave pelo nome-base para valer tanto no manifesto antigo (caminho
    relativo a bruto/) quanto no novo (relativo a dados/, com `estagio`).
    Nome-base repetido com hash diferente é ambíguo e vira erro.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Manifesto não encontrado: {caminho}\n"
            f"Ele é versionado no git; restaure com `git checkout -- dados/MANIFEST.csv`."
        )
    hashes: dict[str, str] = {}
    with caminho.open(encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            nome = pathlib.PurePosixPath(linha["arquivo"]).name
            anterior = hashes.setdefault(nome, linha["sha256"])
            if anterior != linha["sha256"]:
                raise ErroIntegridade(
                    f"Nome-base {nome!r} aparece no manifesto com dois sha256 "
                    f"diferentes ({anterior} e {linha['sha256']})."
                )
    return hashes


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


def _md5_do_inep(zf: zipfile.ZipFile) -> dict[str, str]:
    """{nome em minúsculas: md5} de todos os md5_*.txt do zip."""
    esperados: dict[str, str] = {}
    for info in zf.infolist():
        nome = pathlib.PurePosixPath(info.filename).name
        if nome.lower().startswith("md5_") and nome.lower().endswith(".txt"):
            for membro, md5 in _ler_md5_txt(zf.read(info)).items():
                esperados[membro.lower()] = md5
    return esperados


def extrair_membro(
    zip_path: pathlib.Path, membro: str, destino: pathlib.Path, sha_esperado: str
) -> str:
    """Extrai `membro` (nome-base) de `zip_path` para `destino`.

    Retorna "ja_presente" se `destino` existe e confere, "extraido" se foi
    criado agora. Levanta ErroIntegridade se `destino` existe e diverge (não
    sobrescreve), se o md5 do INEP não confere ou se o sha256 do manifesto
    não confere — nesses dois casos nada é deixado em `destino`.
    """
    if destino.exists():
        obtido = sha256_arquivo(destino)
        if obtido == sha_esperado:
            logger.info("Já presente e íntegro: %s", destino.name)
            return "ja_presente"
        raise ErroIntegridade(
            f"{destino} já existe e não confere com o manifesto — não será sobrescrito.\n"
            f"sha256 esperado: {sha_esperado}\nsha256 obtido:   {obtido}"
        )
    if not zip_path.exists():
        existentes = sorted(p.name for p in zip_path.parent.glob("*.zip")) if zip_path.parent.is_dir() else []
        raise FileNotFoundError(
            f"Zip não encontrado: {zip_path}\nZips em {zip_path.parent}: {existentes or 'nenhum'}"
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + _SUFIXO_PARCIAL)
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with zipfile.ZipFile(zip_path) as zf:
        info = _localizar_membro(zf, membro, zip_path)
        md5_inep = _md5_do_inep(zf).get(membro.lower())
        with zf.open(info) as src, parcial.open("wb") as dst:
            for bloco in iter(lambda: src.read(1 << 20), b""):
                sha.update(bloco)
                md5.update(bloco)
                dst.write(bloco)

    problemas = []
    if md5_inep is not None and md5.hexdigest() != md5_inep:
        problemas.append(f"md5 do INEP esperado: {md5_inep}\nmd5 obtido:           {md5.hexdigest()}")
    if sha.hexdigest() != sha_esperado:
        problemas.append(f"sha256 esperado (manifesto): {sha_esperado}\nsha256 obtido:               {sha.hexdigest()}")
    if problemas:
        parcial.unlink()
        raise ErroIntegridade(
            f"{membro} extraído de {zip_path.name} não confere:\n" + "\n".join(problemas)
        )
    if md5_inep is None:
        logger.warning("%s não tem md5 no zip do INEP; conferido só pelo manifesto.", membro)
    os.replace(parcial, destino)
    logger.info("Extraído e conferido: %s ← %s", destino.name, zip_path.name)
    return "extraido"


def extrair_censo(
    ano: int, origem: pathlib.Path = ORIGEM_CENSO, hashes: dict[str, str] | None = None
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
        status[destino.name] = extrair_membro(zip_path, destino.name, destino, hashes[destino.name])
    return status


def extrair_documentacao(
    origem: pathlib.Path = ORIGEM_CENSO, destino: pathlib.Path = ORIGEM_DOC,
    hashes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Extrai os PDFs de DOCUMENTACAO dos zips de microdados → {arquivo: status}."""
    hashes = hashes if hashes is not None else hashes_manifesto()
    return {
        nome: extrair_membro(origem / MICRODADOS_ZIP[ano], membro, destino / nome, hashes[nome])
        for nome, (ano, membro) in DOCUMENTACAO.items()
    }
