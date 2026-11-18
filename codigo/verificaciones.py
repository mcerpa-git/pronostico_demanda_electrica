"""Validaciones y EDA básica del snapshot horario de demanda."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def detectar_atipicos(
    datos: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Detecta atípicos con la regla del rango intercuartílico (IQR)."""
    registros: list[dict[str, object]] = []
    resumen: dict[str, dict[str, float]] = {}

    for columna in datos.select_dtypes(include="number").columns:
        serie = datos[columna].dropna()
        q1 = float(serie.quantile(0.25))
        q3 = float(serie.quantile(0.75))
        iqr = q3 - q1
        limite_inferior = q1 - 1.5 * iqr
        limite_superior = q3 + 1.5 * iqr
        mascara = (datos[columna] < limite_inferior) | (
            datos[columna] > limite_superior
        )
        resumen[columna] = {
            "q1": q1,
            "q3": q3,
            "limite_inferior": limite_inferior,
            "limite_superior": limite_superior,
            "cantidad": int(mascara.sum()),
            "porcentaje": float(mascara.mean() * 100),
        }
        for timestamp, valor in datos.loc[mascara, columna].items():
            registros.append(
                {
                    "timestamp": timestamp,
                    "variable": columna,
                    "valor": valor,
                    "limite_inferior": limite_inferior,
                    "limite_superior": limite_superior,
                }
            )

    return pd.DataFrame(registros), resumen


def guardar_graficas(datos: pd.DataFrame, carpeta: Path) -> None:
    """Guarda gráficas sencillas para la revisión exploratoria."""
    numericas = datos.select_dtypes(include="number").columns
    figura, ejes = plt.subplots(
        len(numericas), 1, figsize=(14, 4 * len(numericas)), sharex=True
    )
    ejes = [ejes] if len(numericas) == 1 else ejes
    for eje, columna in zip(ejes, numericas):
        eje.plot(datos.index, datos[columna], linewidth=0.7)
        eje.set_title(f"Serie temporal: {columna}")
        eje.set_ylabel(columna)
        eje.grid(alpha=0.3)
    figura.tight_layout()
    figura.savefig(carpeta / "serie_temporal.png", dpi=150)
    plt.close(figura)

    datos[numericas].plot(
        kind="hist", bins=30, subplots=True, figsize=(12, 4 * len(numericas))
    )
    plt.tight_layout()
    plt.savefig(carpeta / "distribuciones.png", dpi=150)
    plt.close()

    datos[numericas].plot(
        kind="box",
        subplots=True,
        layout=(len(numericas), 1),
        figsize=(10, 4 * len(numericas)),
    )
    plt.tight_layout()
    plt.savefig(carpeta / "diagramas_caja.png", dpi=150)
    plt.close()


def ejecutar_verificaciones(
    ruta_csv: str, carpeta_reports: str = "reports"
) -> None:
    """Genera reportes de calidad y EDA para un CSV horario."""
    carpeta = Path(carpeta_reports)
    carpeta.mkdir(parents=True, exist_ok=True)

    datos = pd.read_csv(ruta_csv, parse_dates=["timestamp"])
    if "timestamp" not in datos.columns:
        raise ValueError("El CSV debe contener una columna 'timestamp'.")
    if datos["timestamp"].isna().any():
        raise ValueError("El CSV contiene timestamps que no se pudieron interpretar.")

    timestamps = datos["timestamp"]
    ordenada = bool(timestamps.is_monotonic_increasing)
    duplicados = timestamps[timestamps.duplicated(keep=False)].sort_values()
    datos = datos.set_index("timestamp")

    indice_sin_duplicados = datos.index.drop_duplicates().sort_values()
    indice_esperado = pd.date_range(
        indice_sin_duplicados.min(), indice_sin_duplicados.max(), freq="h"
    )
    faltantes = indice_esperado.difference(indice_sin_duplicados)
    nulos = datos.isna().sum()
    atipicos, resumen_atipicos = detectar_atipicos(datos)

    resumen = pd.DataFrame(
        {
            "indicador": [
                "observaciones",
                "fecha_inicio",
                "fecha_fin",
                "indice_ordenado",
                "timestamps_duplicados",
                "huecos_horarios",
                "valores_nulos_total",
            ],
            "valor": [
                len(datos),
                datos.index.min(),
                datos.index.max(),
                ordenada,
                len(duplicados),
                len(faltantes),
                int(nulos.sum()),
            ],
        }
    )
    resumen.to_csv(carpeta / "resumen_calidad.csv", index=False)
    nulos.rename("cantidad_nulos").to_csv(carpeta / "nulos_por_variable.csv")
    pd.Series(faltantes, name="timestamp").to_csv(
        carpeta / "huecos_horarios.csv", index=False
    )
    duplicados.to_frame(name="timestamp").drop_duplicates().to_csv(
        carpeta / "timestamps_duplicados.csv", index=False
    )
    atipicos.to_csv(carpeta / "valores_atipicos.csv", index=False)
    datos.describe().T.to_csv(carpeta / "estadisticas_descriptivas.csv")
    datos.select_dtypes(include="number").corr().to_csv(carpeta / "correlaciones.csv")
    guardar_graficas(datos, carpeta)

    lineas = [
        "# Reporte de calidad y EDA",
        "",
        f"- Archivo analizado: `{ruta_csv}`",
        f"- Observaciones: **{len(datos)}**",
        f"- Rango: **{datos.index.min()}** a **{datos.index.max()}**",
        f"- Índice ordenado ascendentemente: **{ordenada}**",
        f"- Timestamps duplicados: **{len(duplicados)}**",
        f"- Huecos horarios: **{len(faltantes)}**",
        f"- Valores nulos totales: **{int(nulos.sum())}**",
        "",
        "## Valores atípicos (regla IQR)",
        "",
        "| Variable | Cantidad | Porcentaje | Límite inferior | Límite superior |",
        "|---|---:|---:|---:|---:|",
    ]
    for variable, valores in resumen_atipicos.items():
        lineas.append(
            f"| {variable} | {valores['cantidad']} | "
            f"{valores['porcentaje']:.2f}% | {valores['limite_inferior']:.3f} | "
            f"{valores['limite_superior']:.3f} |"
        )
    lineas.extend(
        [
            "",
            "## Evidencias gráficas",
            "",
            "- `serie_temporal.png`: evolución de las variables.",
            "- `distribuciones.png`: histogramas.",
            "- `diagramas_caja.png`: revisión visual de posibles atípicos.",
            "",
            "Los detalles se encuentran en los archivos CSV de esta carpeta.",
        ]
    )
    (carpeta / "reporte_calidad_eda.md").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", default="datos/xm_demanda.csv")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()
    ejecutar_verificaciones(args.entrada, args.reports)
    print(f"Reportes guardados en: {args.reports}")


if __name__ == "__main__":
    main()