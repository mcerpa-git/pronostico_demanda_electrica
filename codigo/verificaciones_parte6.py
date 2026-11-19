
## Aqui parametrizo las revisiones que hago de manera manual
import argparse
import subprocess

import mlflow
import numpy as np
import pandas as pd
import yaml
from pmdarima import auto_arima
from statsmodels.tsa.statespace.sarimax import SARIMAX

from codigo import ingesta
from pydataxm.pydataxm import ReadDB


def leer_params_commit(commit):
    resultado = subprocess.run(
        ["git", "show", f"{commit}:params.yaml"],
        text=True,
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise ValueError(
            f"No se pudo leer params.yaml en el commit {commit}:\n"
            f"{resultado.stderr.strip()}"
        )
    return yaml.safe_load(resultado.stdout)


def leer_dvc_commit(commit, ruta_descriptor):
    resultado = subprocess.run(
        ["git", "show", f"{commit}:{ruta_descriptor}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise ValueError(
            f"No se pudo leer {ruta_descriptor} en el commit {commit[:8]}:\n"
            f"{resultado.stderr.strip()}"
        )

    descriptor = yaml.safe_load(resultado.stdout)
    if not isinstance(descriptor, dict) or not descriptor.get("outs"):
        raise ValueError(
            f"El descriptor DVC {ruta_descriptor} no contiene outs."
        )
    return str(descriptor["outs"][0]["md5"])


def commits_descendientes(commit):
    resultado = subprocess.run(
        ["git", "rev-list", commit],
        text=True,
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise ValueError(
            f"No se pudo recorrer el historial desde {commit}:"
            f"\n{resultado.stderr.strip()}"
        )
    return resultado.stdout.splitlines()


parser = argparse.ArgumentParser(
    description="Verificaciones manuales de la Parte 6."
)
parser.add_argument(
    "--commit",
    default="HEAD",
    help="Commit del experimento cuyo params.yaml se utilizará.",
)
argumentos = parser.parse_args()

commit_experimento = subprocess.run(
    ["git", "rev-parse", argumentos.commit],
    text=True,
    capture_output=True,
    check=True,
).stdout.strip()
print("*-" * 20)
print("1. Fuga de datos")
print("*-" * 20)
print("verificar las particiones de train y test, si hay fuga de datos")
ruta_csv_train = "datos/train.csv"
ruta_csv_test = "datos/test.csv"
datos_train = pd.read_csv(ruta_csv_train, parse_dates=["timestamp"])
datos_test = pd.read_csv(ruta_csv_test, parse_dates=["timestamp"])
# extraer las fechas de train y test
train_dates = datos_train["timestamp"]
test_dates = datos_test["timestamp"]
print("rango de fechas de train):", train_dates.min(), "a", train_dates.max())
print("rango de fechas de test:", test_dates.min(), "a", test_dates.max())
#verificar si hay fecha de train que este en test
fuga = train_dates.isin(test_dates)
if fuga.any():
    print("Hay fuga de datos, las siguientes fechas de train están en test:")
    print(train_dates[fuga])
else:
    print("No hay fuga de datos entre train y test")
print("*-" * 20)
print("2. Verificar RMSE de uno de los runs")
print("*-" * 20)
commit_parametros = None
configuracion_commit = None
runs = pd.DataFrame()

for candidato in commits_descendientes(commit_experimento):
    try:
        configuracion_candidata = leer_params_commit(candidato)
    except ValueError:
        continue

    mlflow.set_tracking_uri(
        configuracion_candidata["mlflow"]["tracking_uri"]
    )
    experimento = mlflow.set_experiment(
        configuracion_candidata["mlflow"]["experiment_name"]
    )
    runs_candidato = mlflow.search_runs(
        experiment_ids=[experimento.experiment_id],
        filter_string=f"tags.git_commit = '{candidato}'",
        output_format="pandas",
    )
    if not runs_candidato.empty:
        commit_parametros = candidato
        configuracion_commit = configuracion_candidata
        runs = runs_candidato
        break

if runs.empty:
    print(
        "No se encontró un run asociado a "
        f"{commit_experimento} ni a ninguno de sus commits anteriores."
    )
else:
    run_seleccionado = runs.iloc[0]
    run_id = run_seleccionado["run_id"]
    rmse_mlflow = float(run_seleccionado["metrics.rmse_test"])

    modelo_commit = configuracion_commit["model"]
    tipo_modelo = str(modelo_commit.get("tipo_modelo", "sarimax")).lower()
    usar_exogena = bool(modelo_commit["usar_exogena"])

    exog_entrenamiento = None
    exog_prueba = None
    if usar_exogena:
        exog_entrenamiento = datos_train[["temperatura_c"]]
        exog_prueba = datos_test[["temperatura_c"]]

    if tipo_modelo == "autoarima":
        configuracion_auto = modelo_commit["autoarima"]
        ajuste = auto_arima(
            datos_train["demanda_mwh"],
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
        predicho = np.asarray(
            ajuste.predict(
                n_periods=len(datos_test),
                X=exog_prueba,
            ),
            dtype=float,
        )
        order = tuple(int(valor) for valor in ajuste.order)
        seasonal_order = tuple(
            int(valor) for valor in ajuste.seasonal_order
        )
    else:
        order = tuple(
            int(valor) for valor in modelo_commit["order"]
        )
        seasonal_order = tuple(
            int(valor) for valor in modelo_commit["seasonal_order"]
        )
        ajuste = SARIMAX(
            datos_train["demanda_mwh"],
            exog=exog_entrenamiento,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
        pronostico = ajuste.get_forecast(
            steps=len(datos_test),
            exog=exog_prueba,
        )
        predicho = pronostico.predicted_mean.to_numpy()
    real = datos_test["demanda_mwh"].to_numpy()
    predicho = pronostico.predicted_mean.to_numpy()
    rmse_numpy = float(np.sqrt(np.mean(np.square(predicho - real))))

    diferencia = abs(rmse_numpy - rmse_mlflow)
    print("commit seleccionado:", commit_parametros)
    print("order:", order)
    print("seasonal_order:", seasonal_order)
    print("usar_exogena:", usar_exogena)
    print("run_id:", run_id)
    print("RMSE registrado en MLflow:", rmse_mlflow)
    print("RMSE calculado manualmente con NumPy:", rmse_numpy)
    print("Diferencia absoluta:", diferencia)
    if diferencia < 1e-6:
        print("Coincide con el RMSE registrado.")
    else:
        print("No coincide exactamente con el RMSE registrado.")

print("*-" * 20)
print("3. Verificar trazabilidad de los datos DVC")
print("*-" * 20)

if runs.empty:
    print("No hay run seleccionado para comparar el hash DVC.")
else:
    ruta_descriptor = "datos/xm_demanda.csv.dvc"
    dvc_hash_run = str(run_seleccionado["tags.dvc_data_hash"])
    dvc_hash_commit = leer_dvc_commit(
        commit_parametros,
        ruta_descriptor,
    )
    print("commit del descriptor:", commit_parametros)
    print("dvc_data_hash del run:", dvc_hash_run)
    print("MD5 del descriptor en el commit:", dvc_hash_commit)
    if dvc_hash_run == dvc_hash_commit:
        print("Coincide el dvc_data_hash del run con el .dvc del commit.")
    else:
        print("No coincide el dvc_data_hash del run con el .dvc del commit.")

print("*-" * 20)
print("4. Verificar trazabilidad de los parámetros")
print("*-" * 20)
print("Selecciono de manera manual la fecha 2026-08-17 para verificar funcion obtener_demanda_xm")
demanda_xm = ingesta.obtener_demanda_xm(
    inicio=str("2026-08-17"),
    fin=str("2026-08-17"),
)
print("Datos generados")
print("=" * 20)
print(demanda_xm.head())
print(demanda_xm.tail())
print(demanda_xm.shape)
print("Verifico directamente la consutla en la pagina de XM para la fecha 2026-08-17")
print("=" * 20)
respuesta = ReadDB().request_data("DemaCome", "Sistema", str("2026-08-17"), str("2026-08-17"))
if respuesta.empty:
    raise RuntimeError("XM no devolvio datos para el rango solicitado.")
print("Datos obtenidos de XM")
print("=" * 20)
print(respuesta.head())
print(respuesta.shape)

Values_Hour01 = respuesta["Values_Hour01"].values[0]
Values_Hour24 = respuesta["Values_Hour24"].values[0]


def convertir_kwh_a_mwh(valor):
    return float(pd.to_numeric(valor)) / 1000

def obtener_valor_hora(datos, fecha):
    valor = datos.loc[fecha]
    return valor.iloc[0] if isinstance(valor, pd.Series) else valor


tabla_comparativa = pd.DataFrame(
    {
        "hora": ["00:00", "23:00"],
        "XM_directo": [Values_Hour01, Values_Hour24],
        "XM_directo_En_Mwh": [
            convertir_kwh_a_mwh(Values_Hour01),
            convertir_kwh_a_mwh(Values_Hour24),
        ],

        "obtener_demanda_xm": [
            obtener_valor_hora(demanda_xm, "2026-08-17 00:00:00"),
            obtener_valor_hora(demanda_xm, "2026-08-17 23:00:00"),
        ],
    }
)

print("Tabla comparativa de la demanda de la fecha 2026-08-17")
print("=" * 20)
print(tabla_comparativa.to_string(index=False))
print("Verifico si los valores son iguales")
if (
    tabla_comparativa["XM_directo_En_Mwh"]
    == tabla_comparativa["obtener_demanda_xm"]
).all():
    print("Los valores son iguales, la función obtener_demanda_xm funciona correctamente.")
else:
    print("Los valores no son iguales, hay un problema con la función obtener_demanda_xm.")
