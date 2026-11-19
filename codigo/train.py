"""Ajusta SARIMAX y registra la ejecución completa en MLflow."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import yaml
from pmdarima import auto_arima
from statsmodels.tsa.statespace.sarimax import SARIMAX


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]
ENTRENAMIENTO = RAIZ_REPOSITORIO / "datos/train.csv"
PRUEBA = RAIZ_REPOSITORIO / "datos/test.csv"
METRICAS = RAIZ_REPOSITORIO / "metrics.json"
DATOS = RAIZ_REPOSITORIO / "datos/xm_demanda.csv"
DESCRIPTOR = RAIZ_REPOSITORIO / "datos/xm_demanda.csv.dvc"
PARAMETROS = RAIZ_REPOSITORIO / "params.yaml"


def calcular_metricas(real: np.ndarray, predicho: np.ndarray) -> dict[str, float]:
    errores = predicho - real
    rmse = float(np.sqrt(np.mean(np.square(errores))))
    mae = float(np.mean(np.abs(errores)))
    denominador = np.where(np.abs(real) > 1e-12, np.abs(real), np.nan)
    mape = float(np.nanmean(np.abs(errores) / denominador) * 100)
    return {"rmse_test": rmse, "mae_test": mae, "mape_test": mape}


def obtener_git_commit() -> str:
    resultado = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=RAIZ_REPOSITORIO,
        text=True,
        capture_output=True,
        check=True,
    )
    return resultado.stdout.strip()


def obtener_dvc_data_hash() -> str:
    descriptor = yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))
    if not isinstance(descriptor, dict) or not descriptor.get("outs"):
        raise ValueError("No se pudo leer el hash DVC del descriptor.")
    return str(descriptor["outs"][0]["md5"])


def logear_dataset(nombre: str) -> None:
    datos = pd.read_csv(DATOS, parse_dates=["timestamp"])
    dataset = mlflow.data.from_pandas(
        datos,
        source=str(DATOS),
        name=nombre,
    )
    mlflow.log_input(dataset, context="training")


def main() -> None:
    parametros = yaml.safe_load(PARAMETROS.read_text(encoding="utf-8"))
    preparar = parametros["prepare"]
    modelo = parametros["model"]
    mlflow_parametros = parametros["mlflow"]

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

    order = tuple(int(valor) for valor in modelo["order"])
    seasonal_order = tuple(
        int(valor) for valor in modelo["seasonal_order"]
    )
    usar_exogena = bool(modelo["usar_exogena"])
    exog_entrenamiento = None
    exog_prueba = None
    if usar_exogena:
        if "temperatura_c" not in entrenamiento.columns:
            raise ValueError(
                "usar_exogena=true requiere temperatura_c en train.csv."
            )
        if "temperatura_c" not in prueba.columns:
            raise ValueError(
                "usar_exogena=true requiere temperatura_c en test.csv."
            )
        exog_entrenamiento = entrenamiento[["temperatura_c"]]
        exog_prueba = prueba[["temperatura_c"]]

    mlflow.set_tracking_uri(mlflow_parametros["tracking_uri"])
    mlflow.set_experiment(mlflow_parametros["experiment_name"])

    with mlflow.start_run(run_name=mlflow_parametros["run_name"]) as run:
        tipo_modelo = str(modelo["tipo_modelo"]).lower()
        if tipo_modelo == "sarimax":
            ajuste = SARIMAX(
                entrenamiento["demanda_mwh"],
                exog=exog_entrenamiento,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            pronostico = ajuste.get_forecast(
                steps=len(prueba),
                exog=exog_prueba,
            )
            predicho = pronostico.predicted_mean.to_numpy(dtype=float)
            intervalo = pronostico.conf_int(alpha=0.05)
            aic = float(ajuste.aic)
            bic = float(ajuste.bic)
            orden_auto = None
            orden_estacional_auto = None
        elif tipo_modelo == "autoarima":
            configuracion_auto = modelo["autoarima"]
            ajuste = auto_arima(
                entrenamiento["demanda_mwh"],
                X=exog_entrenamiento,
                start_p=int(configuracion_auto["start_p"]),
                max_p=int(configuracion_auto["max_p"]),
                start_q=int(configuracion_auto["start_q"]),
                max_q=int(configuracion_auto["max_q"]),
                d=configuracion_auto["d"],
                max_d=int(configuracion_auto["max_d"]),
                start_P=int(configuracion_auto["start_P"]),
                max_P=int(configuracion_auto["max_P"]),
                start_Q=int(configuracion_auto["start_Q"]),
                max_Q=int(configuracion_auto["max_Q"]),
                D=configuracion_auto["D"],
                max_D=int(configuracion_auto["max_D"]),
                seasonal=bool(configuracion_auto["seasonal"]),
                m=int(configuracion_auto["m"]),
                stepwise=bool(configuracion_auto["stepwise"]),
                with_intercept=bool(
                    configuracion_auto["with_intercept"]
                ),
                suppress_warnings=True,
                error_action="ignore",
            )
            predicho, intervalo = ajuste.predict(
                n_periods=len(prueba),
                X=exog_prueba,
                return_conf_int=True,
                alpha=0.05,
            )
            predicho = np.asarray(predicho, dtype=float)
            intervalo = np.asarray(intervalo, dtype=float)
            aic = float(ajuste.aic())
            bic = float(ajuste.bic())
            orden_auto = tuple(int(valor) for valor in ajuste.order)
            orden_estacional_auto = tuple(
                int(valor) for valor in ajuste.seasonal_order
            )
        else:
            raise ValueError(
                "tipo_modelo debe ser 'sarimax' o 'autoarima'."
            )

        real = prueba["demanda_mwh"].to_numpy(dtype=float)

        metricas = calcular_metricas(real, predicho)
        metricas.update(
            {
                "aic": aic,
                "bic": bic,
            }
        )

        parametros_run = {
            "modelo": tipo_modelo.upper(),
            "usar_exogena": usar_exogena,
            "dias_entrenamiento": int(
                preparar["dias_entrenamiento"]
            ),
            "horas_prueba": int(preparar["horas_prueba"]),
            "train_size": len(entrenamiento),
            "test_size": len(prueba),
        }
        if tipo_modelo == "sarimax":
            parametros_run.update(
                {
                    "order_p": order[0],
                    "order_d": order[1],
                    "order_q": order[2],
                    "seasonal_p": seasonal_order[0],
                    "seasonal_d": seasonal_order[1],
                    "seasonal_q": seasonal_order[2],
                    "seasonal_period": seasonal_order[3],
                }
            )
        else:
            parametros_run.update(
                {
                    "order_p": orden_auto[0],
                    "order_d": orden_auto[1],
                    "order_q": orden_auto[2],
                    "seasonal_p": orden_estacional_auto[0],
                    "seasonal_d": orden_estacional_auto[1],
                    "seasonal_q": orden_estacional_auto[2],
                    "seasonal_period": orden_estacional_auto[3],
                    "autoarima_stepwise": bool(
                        configuracion_auto["stepwise"]
                    ),
                }
            )
        mlflow.log_params(parametros_run)
        mlflow.log_metrics(metricas)
        mlflow.set_tags(
            {
                "dvc_data_hash": obtener_dvc_data_hash(),
                "git_commit": obtener_git_commit(),
                "fuente": mlflow_parametros["fuente"],
                "supuesto_exogena": (
                    "temperatura_observada_en_tramo_prueba"
                    if usar_exogena
                    else "sin_temperatura_exogena"
                ),
            }
        )
        logear_dataset(mlflow_parametros["dataset_name"])

        fig, eje = plt.subplots(figsize=(12, 5))
        eje.plot(prueba.index, real, label="Demanda real")
        eje.plot(prueba.index, predicho, label="Pronóstico SARIMAX")
        if hasattr(intervalo, "iloc"):
            limite_inferior = intervalo.iloc[:, 0].to_numpy()
            limite_superior = intervalo.iloc[:, 1].to_numpy()
        else:
            limite_inferior = intervalo[:, 0]
            limite_superior = intervalo[:, 1]
        eje.fill_between(
            prueba.index,
            limite_inferior,
            limite_superior,
            alpha=0.25,
            label="Intervalo del 95%",
        )
        eje.set_title("Pronóstico contra demanda real")
        eje.set_xlabel("Timestamp")
        eje.set_ylabel("Demanda MWh")
        eje.legend()
        fig.tight_layout()
        mlflow.log_figure(fig, "artifacts/pronostico_vs_real.png")
        plt.close(fig)

        if tipo_modelo == "sarimax":
            fig_residuos = ajuste.plot_diagnostics(figsize=(12, 8))
        else:
            fig_residuos = ajuste.arima_res_.plot_diagnostics(
                figsize=(12, 8)
            )
        mlflow.log_figure(
            fig_residuos,
            "artifacts/diagnostico_residuales.png",
        )
        plt.close(fig_residuos)

        METRICAS.write_text(
            json.dumps(metricas, indent=2) + "\n",
            encoding="utf-8",
        )

        print(json.dumps(metricas, indent=2))
        print(f"MLflow run_id: {run.info.run_id}")


if __name__ == "__main__":
    main()
