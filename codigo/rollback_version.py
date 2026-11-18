"""Restaura una versión histórica de un archivo gestionado por DVC."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import pandas as pd
import yaml


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]


def ejecutar(comando: list[str]) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando desde la raíz del repositorio."""
    return subprocess.run(
        comando,
        cwd=RAIZ_REPOSITORIO,
        text=True,
        capture_output=True,
        check=False,
    )


def obtener_commits(ruta_descriptor: str) -> list[dict[str, str]]:
    """Obtiene, de la más antigua a la más nueva, los commits del descriptor."""
    resultado = ejecutar(
        [
            "git",
            "--no-pager",
            "log",
            "--reverse",
            "--format=%H%x09%s",
            "--",
            ruta_descriptor,
        ]
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip())

    commits: list[dict[str, str]] = []
    for linea in resultado.stdout.strip().splitlines():
        if not linea:
            continue
        hash_commit, asunto = linea.split("\t", 1)
        commits.append({"hash": hash_commit, "asunto": asunto})
    return commits


def obtener_descriptor(ruta_descriptor: str, commit: str) -> dict[str, object]:
    """Lee el descriptor DVC registrado en un commit."""
    resultado = ejecutar(
        ["git", "--no-pager", "show", f"{commit}:{ruta_descriptor}"]
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"No se pudo leer {ruta_descriptor} en {commit[:8]}:\n"
            f"{resultado.stderr.strip()}"
        )

    descriptor = yaml.safe_load(resultado.stdout)
    if not isinstance(descriptor, dict) or "outs" not in descriptor:
        raise RuntimeError(f"Descriptor DVC inválido en {commit[:8]}.")
    return descriptor


def resolver_version(
    destino: str, ruta_descriptor: str, commits: list[dict[str, str]]
) -> dict[str, str]:
    """Resuelve una selección como vN o como hash de commit."""
    destino_normalizado = destino.strip().lower()
    if destino_normalizado.startswith("v"):
        numero_texto = destino_normalizado[1:]
        if not numero_texto.isdigit():
            raise RuntimeError(
                "Una versión debe tener formato v1, v2, v3, etc."
            )
        indice = int(numero_texto)
        if indice < 1 or indice > len(commits):
            raise RuntimeError(
                f"La versión v{indice} no existe; hay "
                f"{len(commits)} versión(es)."
            )
        return commits[indice - 1]

    coincidencias = [
        commit for commit in commits
        if commit["hash"].startswith(destino)
    ]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        raise RuntimeError("El hash proporcionado es ambiguo.")
    raise RuntimeError(
        f"El commit {destino} no se encuentra entre las versiones de "
        f"{ruta_descriptor}."
    )


def listar_versiones(ruta_datos: str, ruta_descriptor: str) -> str:
    """Construye una lista legible de las versiones disponibles."""
    commits = obtener_commits(ruta_descriptor)
    if not commits:
        return f"No se encontraron commits para {ruta_descriptor}."

    lineas = [
        "Versiones disponibles",
        "=" * 21,
        f"Datos: {ruta_datos}",
        f"Descriptor: {ruta_descriptor}",
        "",
    ]
    for indice, commit in enumerate(commits, start=1):
        descriptor = obtener_descriptor(ruta_descriptor, commit["hash"])
        salida = descriptor["outs"][0]
        lineas.extend(
            [
                f"v{indice}",
                f"  Commit: {commit['hash'][:8]}",
                f"  Asunto: {commit['asunto']}",
                f"  MD5: {salida['md5']}",
                f"  Tamaño: {salida['size']} bytes",
            ]
        )
    return "\n".join(lineas)


def verificar_estado(ruta_descriptor: str, ruta_datos: str) -> None:
    """Impide sobrescribir cambios locales todavía sin confirmar."""
    resultado = ejecutar(
        ["git", "--no-pager", "status", "--porcelain", "--", ruta_descriptor]
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip())
    if resultado.stdout.strip():
        raise RuntimeError(
            f"Hay cambios locales en {ruta_descriptor}. "
            "Confirma o conserva esos cambios antes de hacer rollback."
        )

    ruta_archivo = RAIZ_REPOSITORIO / ruta_datos
    if ruta_archivo.exists():
        resultado_dvc = ejecutar(
            [
                str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
                "status",
                ruta_datos,
            ]
        )
        if resultado_dvc.returncode != 0:
            raise RuntimeError(resultado_dvc.stderr.strip())
        if "changed" in resultado_dvc.stdout.lower():
            raise RuntimeError(
                f"Hay cambios locales en {ruta_datos}. Conserva o descarta "
                "el archivo actual antes de hacer rollback."
            )


def calcular_md5(ruta: Path) -> str:
    """Calcula el MD5 real del archivo restaurado."""
    md5 = hashlib.md5()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            md5.update(bloque)
    return md5.hexdigest()


def descartar_cambios(ruta_datos: str, ruta_descriptor: str) -> None:
    """Descarta cambios locales del descriptor y del CSV versionado."""
    restaurar_descriptor = ejecutar(
        [
            "git",
            "restore",
            "--staged",
            "--worktree",
            "--",
            ruta_descriptor,
        ]
    )
    if restaurar_descriptor.returncode != 0:
        raise RuntimeError(
            f"No se pudo descartar el cambio local de {ruta_descriptor}:\n"
            f"{restaurar_descriptor.stderr.strip()}"
        )

    restaurar_datos = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "checkout",
            "--force",
            ruta_datos,
        ]
    )
    if restaurar_datos.returncode != 0:
        raise RuntimeError(
            f"No se pudo descartar el cambio local de {ruta_datos}:\n"
            f"{restaurar_datos.stderr.strip()}"
        )


def restaurar_version(
    destino: str,
    ruta_datos: str,
    ruta_descriptor: str,
    confirmar: bool,
    descartar: bool = False,
) -> str:
    """Restaura una versión en el descriptor y en el archivo de datos."""
    commits = obtener_commits(ruta_descriptor)
    if not commits:
        raise RuntimeError(f"No se encontraron commits para {ruta_descriptor}.")

    seleccion = resolver_version(destino, ruta_descriptor, commits)
    descriptor = obtener_descriptor(ruta_descriptor, seleccion["hash"])
    salida = descriptor["outs"][0]

    if not confirmar and not descartar:
        return (
            "Vista previa del rollback\n"
            "=========================\n"
            f"Versión destino: {destino}\n"
            f"Commit: {seleccion['hash']}\n"
            f"Asunto: {seleccion['asunto']}\n"
            f"MD5: {salida['md5']}\n"
            f"Tamaño: {salida['size']} bytes\n"
            f"Archivo: {ruta_datos}\n\n"
            "Ejecuta nuevamente con --confirmar para aplicar el rollback.\n"
            "Usa --descartar-cambios para descartar cambios locales y "
            "aplicar inmediatamente."
        )

    if descartar:
        descartar_cambios(ruta_datos, ruta_descriptor)
    else:
        verificar_estado(ruta_descriptor, ruta_datos)

    escribir_descriptor = ejecutar(
        [
            "git",
            "--no-pager",
            "show",
            f"{seleccion['hash']}:{ruta_descriptor}",
        ]
    )
    if escribir_descriptor.returncode != 0:
        raise RuntimeError(escribir_descriptor.stderr.strip())
    (RAIZ_REPOSITORIO / ruta_descriptor).write_text(
        escribir_descriptor.stdout, encoding="utf-8"
    )

    bajar_datos = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "pull",
            ruta_datos,
        ]
    )
    if bajar_datos.returncode != 0:
        raise RuntimeError(
            f"No se pudo descargar el contenido desde el remoto DVC:\n"
            f"{bajar_datos.stderr.strip()}"
        )

    restaurar = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "checkout",
            "--force",
            ruta_datos,
        ]
    )
    if restaurar.returncode != 0:
        raise RuntimeError(
            f"No se pudo restaurar {ruta_datos}:\n"
            f"{restaurar.stderr.strip()}"
        )

    ruta_archivo = RAIZ_REPOSITORIO / ruta_datos
    md5_restaurado = calcular_md5(ruta_archivo)
    if md5_restaurado != str(salida["md5"]):
        raise RuntimeError(
            f"El archivo restaurado no coincide con el MD5 esperado:\n"
            f"esperado={salida['md5']}\n"
            f"real={md5_restaurado}"
        )

    estado_dvc = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "status",
            ruta_datos,
        ]
    )
    if estado_dvc.returncode != 0:
        raise RuntimeError(estado_dvc.stderr.strip())
    if "changed" in estado_dvc.stdout.lower():
        raise RuntimeError(
            "DVC todavía considera el archivo restaurado como cambiado:\n"
            f"{estado_dvc.stdout.strip()}"
        )

    datos = pd.read_csv(RAIZ_REPOSITORIO / ruta_datos)
    filas = len(datos)
    rango = "No disponible"
    if "timestamp" in datos.columns:
        datos["timestamp"] = pd.to_datetime(
            datos["timestamp"], errors="coerce"
        )
        if datos["timestamp"].notna().any():
            rango = (
                f"{datos['timestamp'].min()} a "
                f"{datos['timestamp'].max()}"
            )

    return (
        "Rollback aplicado correctamente\n"
        "==============================\n"
        f"Versión restaurada: {destino}\n"
        f"Commit: {seleccion['hash']}\n"
        f"Asunto: {seleccion['asunto']}\n"
        f"MD5: {salida['md5']}\n"
        f"MD5 verificable del archivo: {md5_restaurado}\n"
        f"Tamaño: {salida['size']} bytes\n"
        f"Observaciones/filas: {filas}\n"
        f"Rango de fechas: {rango}\n"
        "\n"
        "Nota: el archivo descriptor fue actualizado, pero no se hizo "
        "`git commit` automáticamente."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destino",
        nargs="?",
        help="Versión v1, v2, v3, ... o un hash de commit.",
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Muestra las versiones disponibles y termina.",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Aplica el rollback. Sin esta opción solo muestra una vista previa.",
    )
    parser.add_argument(
        "--descartar-cambios",
        action="store_true",
        help=(
            "Descarta cambios locales del descriptor y del CSV, "
            "y aplica inmediatamente el rollback."
        ),
    )
    parser.add_argument(
        "--datos",
        default="datos/xm_demanda.csv",
        help="Ruta del archivo versionado dentro del repositorio.",
    )
    parser.add_argument(
        "--descriptor",
        default="datos/xm_demanda.csv.dvc",
        help="Ruta del descriptor DVC dentro del repositorio.",
    )
    args = parser.parse_args()

    try:
        if args.listar:
            print(listar_versiones(args.datos, args.descriptor))
            return
        if not args.destino:
            parser.error("Indica una versión o usa --listar.")
        print(
            restaurar_version(
                args.destino,
                args.datos,
                args.descriptor,
                args.confirmar,
                args.descartar_cambios,
            )
        )
    except (RuntimeError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()