"""Compara los parámetros y las métricas de los runs registrados en MLflow."""

from __future__ import annotations

from pathlib import Path

import mlflow
import yaml


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]
PARAMETROS = RAIZ_REPOSITORIO / "params.yaml"
SALIDA = RAIZ_REPOSITORIO / "comparacion_runs.csv"


def main() -> None:
    parametros = yaml.safe_load(PARAMETROS.read_text(encoding="utf-8"))
    configuracion_mlflow = parametros["mlflow"]

    mlflow.set_tracking_uri(configuracion_mlflow["tracking_uri"])
    experimento = mlflow.set_experiment(
        configuracion_mlflow["experiment_name"]
    )

    runs = mlflow.search_runs(
        experiment_ids=[experimento.experiment_id],
        output_format="pandas",
    )
    if runs.empty:
        raise RuntimeError(
            "No hay runs registrados en el experimento "
            f"'{configuracion_mlflow['experiment_name']}'."
        )

    columnas = [
        columna
        for columna in runs.columns
        if columna == "run_id"
        or columna.startswith("params.")
        or columna.startswith("metrics.")
    ]
    tabla = runs[columnas].copy()
    tabla = tabla.rename(
        columns={
            columna: columna.removeprefix("params.").removeprefix("metrics.")
            for columna in tabla.columns
        }
    )

    if "rmse_test" in tabla.columns:
        tabla = tabla.sort_values("rmse_test", ascending=True)

    tabla.to_csv(SALIDA, index=False, encoding="utf-8")
    print(
        f"Comparación guardada en {SALIDA.relative_to(RAIZ_REPOSITORIO)} "
        f"({len(tabla)} runs)."
    )
    print(tabla.to_string(index=False))


if __name__ == "__main__":
    main()