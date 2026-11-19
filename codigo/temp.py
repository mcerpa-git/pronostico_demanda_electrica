import ingesta
import pandas as pd
from pydataxm.pydataxm import ReadDB

ruta_csv_train = "datos/train.csv"
ruta_csv_test = "datos/test.csv"
datos_train = pd.read_csv(ruta_csv_train, parse_dates=["timestamp"])
datos_test = pd.read_csv(ruta_csv_test, parse_dates=["timestamp"])
# extraer las fechas de train y test
train_dates = datos_train["timestamp"]
test_dates = datos_test["timestamp"]

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
