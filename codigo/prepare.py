"""Divide el snapshot horario en entrenamiento y prueba sin mezclar fechas."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ_REPOSITORIO / "datos/xm_demanda.csv"
SALIDA_ENTRENAMIENTO = RAIZ_REPOSITORIO / "datos/train.csv"
SALIDA_PRUEBA = RAIZ_REPOSITORIO / "datos/test.csv"


def main() -> None:
    parametros = yaml.safe_load(
        (RAIZ_REPOSITORIO / "params.yaml").read_text(encoding="utf-8")
    )
    dias_entrenamiento = int(parametros["prepare"]["dias_entrenamiento"])
    horas_prueba = int(parametros["prepare"]["horas_prueba"])

    if dias_entrenamiento < 1:
        raise ValueError("dias_entrenamiento debe ser mayor o igual a 1.")
    if horas_prueba < 1:
        raise ValueError("horas_prueba debe ser mayor o igual a 1.")

    datos = pd.read_csv(ENTRADA, parse_dates=["timestamp"]).sort_values(
        "timestamp"
    )
    if datos["timestamp"].duplicated().any():
        raise ValueError("La entrada contiene timestamps duplicados.")

    datos = datos.set_index("timestamp")
    indice_esperado = pd.date_range(
        datos.index.min(), datos.index.max(), freq="h"
    )
    if not datos.index.equals(indice_esperado):
        raise ValueError("El índice horario de entrada no es regular.")

    if len(datos) < dias_entrenamiento * 24 + horas_prueba:
        raise ValueError(
            "No hay suficientes observaciones para "
            "dias_entrenamiento + horas_prueba."
        )

    corte = datos.index[-horas_prueba]
    prueba = datos.loc[corte:]
    inicio_entrenamiento = corte - pd.offsets.Day(dias_entrenamiento)
    entrenamiento = datos.loc[: corte - pd.offsets.Hour(1)].loc[
        inicio_entrenamiento:
    ]

    if len(prueba) != horas_prueba:
        raise RuntimeError("El tramo de prueba no tiene las horas esperadas.")

    SALIDA_ENTRENAMIENTO.parent.mkdir(parents=True, exist_ok=True)
    entrenamiento.to_csv(SALIDA_ENTRENAMIENTO)
    prueba.to_csv(SALIDA_PRUEBA)

    print(
        f"Entrenamiento: {len(entrenamiento)} filas, "
        f"{entrenamiento.index.min()} a {entrenamiento.index.max()}"
    )
    print(
        f"Prueba: {len(prueba)} filas, "
        f"{prueba.index.min()} a {prueba.index.max()}"
    )


if __name__ == "__main__":
    main()
