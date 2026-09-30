"""Aquisição dos dados do INEP: zips em dados/origem/ → arquivos em dados/bruto/.

Cria em dados/origem/ e dados/bruto/ só o que não existe (CLAUDE.md §3,
regra 1): toda escrita passa por src/integridade.py:gravar_conferido.

Camada de extração (esta versão). Dos zips de microdados sai só o que o
projeto usa, com o nome exato do INEP (inclusive o `.CSV` maiúsculo de 2020):
o arquivo de escolas de cada ano e, em 2025, também Turma, Matrícula e
Docente. Cada arquivo é conferido contra o sha256 de dados/MANIFEST.csv e
contra o md5_*.txt do próprio INEP dentro do zip.

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

import argparse
import logging
import pathlib
import zipfile

from src.config import ARQUIVOS, ORIGEM_CENSO, ORIGEM_DOC
from src.integridade import (
    ErroIntegridade,
    Referencia,
    confere_existente,
    gravar_conferido,
    hashes_manifesto,
    md5_do_zip,
)

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
        ref = Referencia(sha_esperado, md5_do_zip(zf).get(membro.lower()), info.CRC)
        with zf.open(info) as fonte:
            status = gravar_conferido(fonte, destino, ref, sobrescrever=sobrescrever,
                                      descricao=f"de {zip_path.name}").status
    logger.info("%s: %s ← %s", status, destino.name, zip_path.name)
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Extrai os microdados de dados/origem/censo/ para dados/bruto/censo/.")
    ap.add_argument("--anos", type=int, nargs="+", default=sorted(MICRODADOS_ZIP))
    ap.add_argument("--sobrescrever", action="store_true",
                    help="regrava arquivos já presentes (CLAUDE.md §3, regra 1)")
    args = ap.parse_args()
    hashes = hashes_manifesto()
    for ano in args.anos:
        extrair_censo(ano, hashes=hashes, sobrescrever=args.sobrescrever)
    extrair_documentacao(hashes=hashes, sobrescrever=args.sobrescrever)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
