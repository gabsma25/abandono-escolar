"""Conferência de hash e escrita segura em pastas imutáveis (CLAUDE.md §3, regra 1).

dados/origem/, dados/bruto/ e dados/externo/ só recebem arquivo por
`gravar_conferido`: arquivo presente cujo hash confere nunca é tocado (nem o
mtime muda); arquivo presente que diverge é erro; arquivo novo é escrito em
`<nome>.parcial`, conferido e só então renomeado. O que não confere vai para
dados/cache_download/divergente/ e nunca entra nas pastas imutáveis.
Regravação só com `sobrescrever=True` (flag --sobrescrever na linha de comando).

Referência de hash, na ordem:
  1. sha256 de dados/MANIFEST.csv — o gabarito do projeto;
  2. md5 do md5_*.txt do INEP — para arquivo que ainda não está no manifesto;
  3. CRC32 do membro no zip — quando não há nenhum dos dois.
Se o manifesto confere e o md5 do INEP não, é aviso, não erro: o INEP publica
md5 desatualizado em alguns zips (P007, P020) e o manifesto já registra o
arquivo que o projeto validou.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import pathlib
import re
import zipfile
import zlib
from dataclasses import dataclass
from typing import IO

from src.config import DIVERGENTE, MANIFEST

logger = logging.getLogger(__name__)

SUFIXO_PARCIAL = ".parcial"
_LINHA_MD5 = re.compile(r"^(?P<md5>[0-9a-f]{32})\s+\*?(?P<nome>.+?)\s*$", re.IGNORECASE)


class ErroIntegridade(RuntimeError):
    """Hash divergente, membro ausente ou arquivo existente que não confere."""


@dataclass(frozen=True)
class Referencia:
    """Hashes esperados de um arquivo; qualquer um pode faltar."""
    sha256_manifesto: str | None = None
    md5_inep: str | None = None
    crc32_zip: int | None = None


@dataclass(frozen=True)
class Digestos:
    sha256: str
    md5: str
    crc32: int


@dataclass(frozen=True)
class Resultado:
    status: str          # "ja_presente", "extraido" ou "sobrescrito"
    digestos: Digestos   # do arquivo que ficou em `destino`


def digestos(caminho: pathlib.Path) -> Digestos:
    sha, md5, crc = hashlib.sha256(), hashlib.md5(), 0
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            sha.update(bloco)
            md5.update(bloco)
            crc = zlib.crc32(bloco, crc)
    return Digestos(sha.hexdigest(), md5.hexdigest(), crc)


def sha256_arquivo(caminho: pathlib.Path) -> str:
    return digestos(caminho).sha256


def ler_md5_txt(conteudo: bytes) -> dict[str, str]:
    """Interpreta o md5_*.txt do INEP: linhas 'hash *nome_do_arquivo'."""
    esperados: dict[str, str] = {}
    for linha in conteudo.decode("utf-8", errors="replace").splitlines():
        m = _LINHA_MD5.match(linha.strip())
        if m:
            esperados[m.group("nome")] = m.group("md5").lower()
    return esperados


def md5_do_zip(zf: zipfile.ZipFile) -> dict[str, str]:
    """{nome em minúsculas: md5} de todos os .txt do zip no formato md5sum.
    Qualquer .txt, não só md5_*.txt: em tx_rend_escolas_2023.zip o arquivo de
    md5 se chama tx_rend_escolas_2023.txt. Chave em minúsculas porque o INEP
    grafa '.csv' para '.CSV', '_v2' para '_V2', '.xlsX' para '.xlsx'."""
    esperados: dict[str, str] = {}
    for info in zf.infolist():
        if pathlib.PurePosixPath(info.filename).suffix.lower() == ".txt":
            for membro, md5 in ler_md5_txt(zf.read(info)).items():
                esperados[membro.lower()] = md5
    return esperados


def hashes_manifesto(caminho: pathlib.Path = MANIFEST) -> dict[str, str]:
    """{nome-base do arquivo: sha256} de dados/MANIFEST.csv.

    Chave pelo nome-base: o nome original do INEP é único no projeto.
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


def _divergencias(d: Digestos, ref: Referencia) -> tuple[list[str], list[str]]:
    """(erros, avisos) de `d` contra `ref`, pela ordem de autoridade."""
    erros: list[str] = []
    avisos: list[str] = []
    md5_diverge = ref.md5_inep is not None and d.md5 != ref.md5_inep
    if ref.sha256_manifesto is not None:
        if d.sha256 != ref.sha256_manifesto:
            erros.append(f"sha256 esperado (manifesto): {ref.sha256_manifesto}\n"
                         f"sha256 obtido:               {d.sha256}")
        elif md5_diverge:
            avisos.append(f"md5 do INEP ({ref.md5_inep}) não confere, mas o sha256 do "
                          f"manifesto confere (md5 publicado desatualizado, cf. P007/P020)")
    elif md5_diverge:
        erros.append(f"md5 esperado (INEP): {ref.md5_inep}\nmd5 obtido:          {d.md5}")
    elif ref.md5_inep is None and ref.crc32_zip is not None and d.crc32 != ref.crc32_zip:
        erros.append(f"CRC32 esperado (zip): {ref.crc32_zip:08x}\nCRC32 obtido:         {d.crc32:08x}")
    return erros, avisos


def confere_existente(destino: pathlib.Path, ref: Referencia) -> Digestos | None:
    """Digestos de `destino` se ele existe e confere (só leitura: mtime
    intocado); None se não existe. Levanta ErroIntegridade se existe e diverge."""
    if not destino.exists():
        return None
    d = digestos(destino)
    erros, avisos = _divergencias(d, ref)
    if erros:
        raise ErroIntegridade(
            f"{destino} já existe e não confere — não será regravado "
            f"(use --sobrescrever se for intencional).\n" + "\n".join(erros)
        )
    for a in avisos:
        logger.warning("%s: %s", destino.name, a)
    return d


def _para_divergente(parcial: pathlib.Path, nome: str, d: Digestos) -> pathlib.Path:
    DIVERGENTE.mkdir(parents=True, exist_ok=True)
    alvo = DIVERGENTE / f"{nome}.{d.sha256[:12]}"
    os.replace(parcial, alvo)
    return alvo


def gravar_conferido(
    fonte: IO[bytes], destino: pathlib.Path, ref: Referencia, *,
    sobrescrever: bool = False, descricao: str = "",
) -> Resultado:
    """Grava o conteúdo de `fonte` em `destino` pela regra 1.

    Status "ja_presente" (existe e confere; nada é escrito), "extraido"
    (criado agora) ou "sobrescrito". Levanta ErroIntegridade se `destino`
    existe e diverge (sem `sobrescrever`) ou se o conteúdo novo não confere
    com `ref` — nesse caso ele vai para cache_download/divergente/.
    """
    existe = destino.exists()
    if existe and not sobrescrever:
        d = confere_existente(destino, ref)
        logger.info("Já presente e íntegro, não tocado: %s", destino.name)
        return Resultado("ja_presente", d)  # type: ignore[arg-type]

    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + SUFIXO_PARCIAL)
    with parcial.open("wb") as dst:
        for bloco in iter(lambda: fonte.read(1 << 20), b""):
            dst.write(bloco)
    d = digestos(parcial)
    erros, avisos = _divergencias(d, ref)
    if erros:
        alvo = _para_divergente(parcial, destino.name, d)
        raise ErroIntegridade(
            f"{destino.name}{' (' + descricao + ')' if descricao else ''} não confere; "
            f"guardado em {alvo}, fora das pastas imutáveis.\n" + "\n".join(erros)
        )
    for a in avisos:
        logger.warning("%s: %s", destino.name, a)
    if ref.sha256_manifesto is None and ref.md5_inep is None and ref.crc32_zip is None:
        logger.warning("%s sem nenhum hash de referência; gravado sem conferência.", destino.name)
    os.replace(parcial, destino)
    return Resultado("sobrescrito" if existe else "extraido", d)
