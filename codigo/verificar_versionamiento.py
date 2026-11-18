"""Compara versiones DVC de un archivo a partir de sus commits de Git."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import yaml


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]


def ejecutar(comando: list[str]) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando dentro de la raíz del repositorio."""
    return subprocess.run(
        comando,
        cwd=RAIZ_REPOSITORIO,
        text=True,
        capture_output=True,
        check=False,
    )


def obtener_commits(ruta_descriptor: str, cantidad: int) -> list[dict[str, str]]:
    """Obtiene los commits más recientes que modificaron el descriptor DVC."""
    resultado = ejecutar(
        [
            "git",
            "--no-pager",
            "log",
            f"-n{cantidad}",
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
        commit, asunto = linea.split("\t", 1)
        commits.append({"hash": commit, "asunto": asunto})
    return list(reversed(commits))


def obtener_descriptor(ruta_descriptor: str, commit: str) -> dict[str, object]:
    """Lee el descriptor DVC de un commit sin modificar el workspace."""
    resultado = ejecutar(
        ["git", "--no-pager", "show", f"{commit}:{ruta_descriptor}"]
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"No se pudo leer {ruta_descriptor} en {commit[:8]}:\n"
            f"{resultado.stderr.strip()}"
        )
    contenido = yaml.safe_load(resultado.stdout)
    if not isinstance(contenido, dict) or "outs" not in contenido:
        raise RuntimeError(f"Descriptor DVC inválido en {commit[:8]}.")
    return contenido


def obtener_datos(ruta_datos: str, commit: str, destino: Path) -> pd.DataFrame:
    """Descarga un CSV histórico con DVC sin cambiar el workspace."""
    resultado = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "get",
            str(RAIZ_REPOSITORIO),
            ruta_datos,
            "--rev",
            commit,
            "--out",
            str(destino),
            "--force",
        ]
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"No se pudieron obtener los datos de {commit[:8]}:\n"
            f"{resultado.stderr.strip()}"
        )

    datos = pd.read_csv(destino)
    if "timestamp" in datos.columns:
        datos["timestamp"] = pd.to_datetime(datos["timestamp"], errors="coerce")
    return datos


def obtener_dvc_diff(
    revision_anterior: str, revision_nueva: str, ruta_datos: str
) -> str:
    """Obtiene el diff DVC entre dos commits."""
    resultado = ejecutar(
        [
            str(RAIZ_REPOSITORIO / ".venv/bin/dvc"),
            "diff",
            revision_anterior,
            revision_nueva,
            "--targets",
            ruta_datos,
            "--show-hash",
        ]
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip())
    return resultado.stdout.strip() or "Sin cambios reportados por DVC."


def generar_reporte(ruta_datos: str, ruta_descriptor: str, cantidad: int) -> str:
    """Construye el reporte textual de todas las versiones solicitadas."""
    commits = obtener_commits(ruta_descriptor, cantidad)
    if not commits:
        raise RuntimeError(f"No se encontraron commits para {ruta_descriptor}.")

    lineas = [
        "REPORTE DE VERSIONAMIENTO DE DATOS",
        "=" * 34,
        f"Archivo versionado: {ruta_datos}",
        f"Descriptor DVC: {ruta_descriptor}",
        f"Commits solicitados: {cantidad}",
        f"Commits encontrados: {len(commits)}",
        "",
    ]

    with tempfile.TemporaryDirectory(prefix="dvc-versiones-") as directorio:
        versiones: list[dict[str, object]] = []
        temporal = Path(directorio)

        for indice, commit in enumerate(commits, start=1):
            descriptor = obtener_descriptor(ruta_descriptor, commit["hash"])
            salida = descriptor["outs"][0]
            archivo_temporal = temporal / f"version_{indice}.csv"
            datos = obtener_datos(
                ruta_datos, commit["hash"], archivo_temporal
            )

            md5 = str(salida["md5"])
            tamano = int(salida["size"])
            filas = len(datos)
            rango = "No disponible"
            if "timestamp" in datos.columns and datos["timestamp"].notna().any():
                rango = (
                    f"{datos['timestamp'].min()} a "
                    f"{datos['timestamp'].max()}"
                )

            versiones.append(
                {
                    "indice": indice,
                    "commit": commit["hash"],
                    "asunto": commit["asunto"],
                    "md5": md5,
                    "tamano": tamano,
                    "filas": filas,
                    "rango": rango,
                }
            )

            lineas.extend(
                [
                    f"Versión v{indice}",
                    "-" * 16,
                    f"Commit: {commit['hash'][:8]}",
                    f"Asunto: {commit['asunto']}",
                    f"MD5: {md5}",
                    f"Tamaño: {tamano} bytes",
                    f"Observaciones/filas: {filas}",
                    f"Rango de fechas: {rango}",
                    "",
                ]
            )

        if len(versiones) < 2:
            lineas.extend(
                [
                    "Comparaciones",
                    "-" * 16,
                    "No hay suficientes commits para realizar comparaciones.",
                    "Se necesita al menos un par de commits.",
                ]
            )
            return "\n".join(lineas)

        lineas.extend(
            ["COMPARACIONES ENTRE VERSIONES", "=" * 32, ""]
        )
        for anterior, nueva in zip(versiones, versiones[1:]):
            lineas.extend(
                [
                    f"Comparación v{anterior['indice']} -> v{nueva['indice']}",
                    "-" * 32,
                    f"Commits: {anterior['commit'][:8]} -> "
                    f"{nueva['commit'][:8]}",
                    f"Hash: {anterior['md5']} -> {nueva['md5']}",
                    f"Tamaño: {anterior['tamano']} -> "
                    f"{nueva['tamano']} bytes",
                    f"Observaciones: {anterior['filas']} -> "
                    f"{nueva['filas']} filas",
                ]
            )

            diferencia_tamano = int(nueva["tamano"]) - int(anterior["tamano"])
            diferencia_filas = int(nueva["filas"]) - int(anterior["filas"])
            lineas.extend(
                [
                    f"Variación de tamaño: {diferencia_tamano:+d} bytes",
                    f"Variación de filas: {diferencia_filas:+d}",
                ]
            )

            if anterior["md5"] == nueva["md5"]:
                lineas.append("Resultado: los datos son idénticos.")
            else:
                lineas.append("Resultado: los datos cambiaron.")

            diff = obtener_dvc_diff(
                str(anterior["commit"]),
                str(nueva["commit"]),
                ruta_datos,
            )
            lineas.extend(["Salida de dvc diff:", diff, ""])

    lineas.extend(
        [
            "Criterio de revisión",
            "-" * 32,
            "- Hash distinto: el contenido de los snapshots cambió.",
            "- Filas distintas: se modificó la extensión temporal o hubo depuración.",
            "- Tamaño distinto: el volumen almacenado cambió.",
        ]
    )
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "cantidad",
        nargs="?",
        type=int,
        default=2,
        help="Número de commits recientes del archivo DVC a comparar.",
    )
    parser.add_argument(
        "--datos",
        default="datos/xm_demanda.csv",
        help="Ruta del archivo versionado dentro del repositorio.",
    )
    parser.add_argument(
        "--descriptor",
        default="datos/xm_demanda.csv.dvc",
        help="Ruta del archivo descriptor DVC dentro del repositorio.",
    )
    args = parser.parse_args()

    if args.cantidad < 1:
        parser.error("La cantidad debe ser mayor o igual a 1.")

    try:
        print(generar_reporte(args.datos, args.descriptor, args.cantidad))
    except (RuntimeError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()