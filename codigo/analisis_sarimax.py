"""Análisis previo para justificar parámetros de SARIMAX."""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, kpss


def ejecutar_prueba_adf(serie: pd.Series) -> tuple[float, float, bool]:
    estadistico, p_valor, *_ = adfuller(
        serie.dropna(),
        autolag="AIC",
        result_object=False,
    )
    return float(estadistico), float(p_valor), p_valor < 0.05


def ejecutar_prueba_kpss(serie: pd.Series) -> tuple[float, float, bool]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        estadistico, p_valor, *_ = kpss(
            serie.dropna(), regression="c", nlags="auto"
        )
    return float(estadistico), float(p_valor), p_valor >= 0.05


def guardar_acf_pacf(
    serie: pd.Series,
    carpeta: Path,
    periodo: int,
    prefijo: str,
) -> None:
    figura, ejes = plt.subplots(2, 1, figsize=(12, 7))
    plot_acf(
        serie.dropna(),
        lags=min(3 * periodo, len(serie) // 2 - 1),
        ax=ejes[0],
    )
    plot_pacf(
        serie.dropna(),
        lags=min(3 * periodo, len(serie) // 2 - 1),
        ax=ejes[1],
        method="ywadjusted",
    )
    ejes[0].set_title(f"ACF - {prefijo}")
    ejes[1].set_title(f"PACF - {prefijo}")
    figura.tight_layout()
    figura.savefig(carpeta / f"{prefijo}_acf_pacf.png", dpi=150)
    plt.close(figura)


def guardar_descomposicion(
    serie: pd.Series,
    carpeta: Path,
    periodo: int,
) -> None:
    descomposicion = seasonal_decompose(
        serie, model="additive", period=periodo
    )
    descomposicion.plot()
    figura = plt.gcf()
    figura.set_size_inches(12, 9)
    figura.tight_layout()
    figura.savefig(
        carpeta / "descomposicion_estacional.png",
        dpi=150,
    )
    plt.close(figura)


def ejecutar_analisis(
    ruta_csv: str,
    carpeta_reports: str,
    periodo: int,
) -> None:
    carpeta = Path(carpeta_reports)
    carpeta.mkdir(parents=True, exist_ok=True)

    datos = pd.read_csv(ruta_csv, parse_dates=["timestamp"]).sort_values(
        "timestamp"
    )
    if "demanda_mwh" not in datos.columns:
        raise ValueError("El CSV debe contener la columna demanda_mwh.")
    if datos["timestamp"].duplicated().any():
        raise ValueError("El CSV contiene timestamps duplicados.")

    datos = datos.set_index("timestamp")
    serie = datos["demanda_mwh"].asfreq("h").dropna()

    indice_esperado = pd.date_range(
        serie.index.min(), serie.index.max(), freq="h"
    )
    if not serie.index.equals(indice_esperado):
        raise ValueError(
            "La demanda debe tener un índice horario regular antes del análisis."
        )

    guardar_acf_pacf(serie, carpeta, periodo, "original")
    guardar_descomposicion(serie, carpeta, periodo)

    diferenciada_24 = serie.diff(periodo).dropna()
    diferenciada_regular = serie.diff().dropna()
    diferenciada_regular_estacional = (
        serie.diff().diff(periodo).dropna()
    )

    guardar_acf_pacf(
        diferenciada_regular_estacional,
        carpeta,
        periodo,
        "diferencia_regular_estacional",
    )

    perfil_hora = serie.groupby(serie.index.hour).agg(["mean", "std", "count"])
    perfil_hora.to_csv(carpeta / "perfil_horario.csv")
    perfil_hora.plot(
        y="mean",
        yerr="std",
        kind="line",
        figsize=(12, 5),
        marker="o",
        capsize=3,
    )
    plt.title("Demanda promedio por hora del día")
    plt.xlabel("Hora del día")
    plt.ylabel("Demanda MWh")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(carpeta / "perfil_horario.png", dpi=150)
    plt.close()

    series_estacionariedad = {
        "original": serie,
        "diferencia_regular": diferenciada_regular,
        "diferencia_estacional_24": diferenciada_24,
        "diferencia_regular_estacional": diferenciada_regular_estacional,
    }
    filas = []
    for nombre, muestra in series_estacionariedad.items():
        adf_estadistico, adf_p, adf_estacionaria = ejecutar_prueba_adf(muestra)
        kpss_estadistico, kpss_p, kpss_estacionaria = ejecutar_prueba_kpss(muestra)
        filas.append(
            {
                "transformacion": nombre,
                "observaciones": len(muestra),
                "adf_estadistico": adf_estadistico,
                "adf_p_valor": adf_p,
                "adf_rechaza_raiz_unitaria": adf_estacionaria,
                "kpss_estadistico": kpss_estadistico,
                "kpss_p_valor": kpss_p,
                "kpss_no_rechaza_estacionaria": kpss_estacionaria,
                "ambas_coinciden_estacionaria": (
                    adf_estacionaria and kpss_estacionaria
                ),
            }
        )
    pd.DataFrame(filas).to_csv(
        carpeta / "pruebas_estacionariedad.csv",
        index=False,
    )

    prueba_principal = next(
        fila for fila in filas if fila["transformacion"] == "original"
    )
    diferencia_regular = next(
        fila
        for fila in filas
        if fila["transformacion"] == "diferencia_regular"
    )
    diferencia_estacional = next(
        fila
        for fila in filas
        if fila["transformacion"] == "diferencia_estacional_24"
    )
    diferencia_total = next(
        fila
        for fila in filas
        if fila["transformacion"] == "diferencia_regular_estacional"
    )

    lineas = [
        "# Evidencia previa para selección de SARIMAX",
        "",
        f"- Archivo analizado: `{ruta_csv}`",
        f"- Observaciones originales: **{len(serie)}**",
        f"- Periodo estacional evaluado: **{periodo} horas**",
        f"- Rango: **{serie.index.min()}** a **{serie.index.max()}**",
        "",
        "## Estacionariedad",
        "",
        "| Transformación | ADF p-valor | KPSS p-valor | Ambas indican estacionaria |",
        "|---|---:|---:|:---:|",
    ]
    for fila in filas:
        lineas.append(
            f"| {fila['transformacion']} | "
            f"{fila['adf_p_valor']:.6f} | "
            f"{fila['kpss_p_valor']:.6f} | "
            f"{'Sí' if fila['ambas_coinciden_estacionaria'] else 'No'} |"
        )

    lineas.extend(
        [
            "",
            "Interpretación:",
            f"- Serie original estacionaria según ambas pruebas: "
            f"{'Sí' if prueba_principal['ambas_coinciden_estacionaria'] else 'No'}.",
            f"- Diferencia regular estacionaria según ambas pruebas: "
            f"{'Sí' if diferencia_regular['ambas_coinciden_estacionaria'] else 'No'}.",
            f"- Diferencia estacional de 24 horas estacionaria según ambas pruebas: "
            f"{'Sí' if diferencia_estacional['ambas_coinciden_estacionaria'] else 'No'}.",
            f"- Diferencia regular y estacional estacionaria según ambas pruebas: "
            f"{'Sí' if diferencia_total['ambas_coinciden_estacionaria'] else 'No'}.",
            "",
            "Esta información orienta los valores iniciales de `d`, `D` y el "
            "periodo estacional `s=24`, pero no reemplaza la comparación de "
            "configuraciones sobre el conjunto de prueba.",
            "",
            "## Evidencias gráficas",
            "",
            "- `original_acf_pacf.png`: autocorrelación y autocorrelación parcial.",
            "- `diferencia_regular_estacional_acf_pacf.png`: rezagos después de diferencias.",
            "- `descomposicion_estacional.png`: tendencia, estacionalidad y residuos.",
            "- `perfil_horario.png`: demanda promedio por hora del día.",
            "",
            "Los valores numéricos están en `pruebas_estacionariedad.csv` y "
            "`perfil_horario.csv`.",
        ]
    )
    (carpeta / "analisis_sarimax.md").write_text(
        "\n".join(lineas) + "\n",
        encoding="utf-8",
    )

    print(f"Evidencias guardadas en: {carpeta}")
    print(f"Observaciones analizadas: {len(serie)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", default="datos/xm_demanda.csv")
    parser.add_argument("--reports", default="reports")
    parser.add_argument(
        "--periodo",
        type=int,
        default=24,
        help="Periodo estacional horario.",
    )
    args = parser.parse_args()
    ejecutar_analisis(args.entrada, args.reports, args.periodo)


if __name__ == "__main__":
    main()
