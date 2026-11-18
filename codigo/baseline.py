"""Calcula el baseline estacional naive de 24 horas."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]
ENTRENAMIENTO = RAIZ_REPOSITORIO / "datos/train.csv"
PRUEBA = RAIZ_REPOSITORIO / "datos/test.csv"
METRICAS = RAIZ_REPOSITORIO / "metrics.json"


def calcular_metricas(real: np.ndarray, predicho: np.ndarray) -> dict[str, float]:
    errores = predicho - real
    rmse = float(np.sqrt(np.mean(np.square(errores))))
    mae = float(np.mean(np.abs(errores)))
    return {"rmse": rmse, "mae": mae}


def main() -> None:
    entrenamiento = pd.read_csv(
        ENTRENAMIENTO, parse_dates=["timestamp"]
    ).set_index("timestamp")
    prueba = pd.read_csv(
        PRUEBA, parse_dates=["timestamp"]
    ).set_index("timestamp")

    if "demanda_mwh" not in entrenamiento.columns:
        raise ValueError("train.csv debe contener la columna demanda_mwh.")
    if "demanda_mwh" not in prueba.columns:
        raise ValueError("test.csv debe contener la columna demanda_mwh.")

    historial = pd.concat(
        [entrenamiento["demanda_mwh"], prueba["demanda_mwh"]]
    )
    prediccion = []
    for timestamp in prueba.index:
        momento_anterior = timestamp - pd.offsets.Hour(24)
        if momento_anterior not in historial.index:
            raise ValueError(
                f"No existe el valor hace 24 horas para {timestamp}."
            )
        prediccion.append(float(historial.loc[momento_anterior]))

    metricas = calcular_metricas(
        prueba["demanda_mwh"].to_numpy(),
        np.asarray(prediccion),
    )
    METRICAS.write_text(
        json.dumps(metricas, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metricas, indent=2))


if __name__ == "__main__":
    main()
