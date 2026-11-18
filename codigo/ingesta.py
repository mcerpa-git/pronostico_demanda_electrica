"""Ingesta de demanda horaria de XM y temperatura de Open-Meteo."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from pydataxm.pydataxm import ReadDB


OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
BOGOTA = {"nombre": "Bogota", "latitud": 4.7110, "longitud": -74.0721}


def obtener_demanda_xm(inicio: str, fin: str) -> pd.DataFrame:
    """Consulta XM y devuelve demanda MWh con índice horario."""
    respuesta = ReadDB().request_data("DemaCome", "Sistema", inicio, fin)
    if respuesta.empty:
        raise RuntimeError("XM no devolvio datos para el rango solicitado.")

    columnas_hora = [
        columna
        for columna in respuesta.columns
        if columna.startswith("Values_Hour")
    ]
    if len(columnas_hora) != 24:
        raise ValueError(
            "Se esperaban 24 columnas horarias de XM; "
            f"se encontraron {len(columnas_hora)}."
        )

    datos = respuesta.melt(
        id_vars=["Date"],
        value_vars=sorted(columnas_hora),
        var_name="hora",
        value_name="demanda_kwh",
    )
    datos["hora"] = datos["hora"].str.extract(r"(\d+)$").astype(int) - 1
    datos["timestamp"] = (
        pd.to_datetime(datos["Date"]) + pd.to_timedelta(datos["hora"], unit="h")
    )
    datos["demanda_mwh"] = pd.to_numeric(datos["demanda_kwh"], errors="coerce") / 1000

    demanda = datos.set_index("timestamp")["demanda_mwh"].sort_index()
    if demanda.index.has_duplicates:
        raise ValueError("La demanda de XM contiene timestamps duplicados.")
    if demanda.isna().any():
        raise ValueError("La demanda de XM contiene valores nulos.")
    return demanda.to_frame()


def obtener_temperatura(
    inicio: str,
    fin: str,
    *,
    latitud: float,
    longitud: float,
) -> pd.DataFrame:
    """Consulta temperatura horaria en grados Celsius."""
    parametros = {
        "latitude": latitud,
        "longitude": longitud,
        "start_date": inicio,
        "end_date": fin,
        "hourly": "temperature_2m",
        "timezone": "America/Bogota",
    }
    respuesta = requests.get(OPEN_METEO_URL, params=parametros, timeout=30)
    respuesta.raise_for_status()
    contenido = respuesta.json()
    if "hourly" not in contenido:
        raise RuntimeError("Open-Meteo no devolvio la serie horaria esperada.")

    horario = contenido["hourly"]
    temperatura = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(horario["time"]),
            "temperatura_c": horario["temperature_2m"],
        }
    ).set_index("timestamp")
    return temperatura


def construir_snapshot(inicio: str, fin: str) -> pd.DataFrame:
    """Construye y valida el snapshot horario conjunto."""
    demanda = obtener_demanda_xm(inicio, fin)
    temperatura = obtener_temperatura(
        inicio,
        fin,
        latitud=BOGOTA["latitud"],
        longitud=BOGOTA["longitud"],
    )

    datos = demanda.join(temperatura, how="left")
    indice_esperado = pd.date_range(
        datos.index.min(), datos.index.max(), freq="h"
    )
    datos = datos.reindex(indice_esperado)

    faltantes_temperatura = int(datos["temperatura_c"].isna().sum())
    if faltantes_temperatura:
        datos["temperatura_c"] = (
            datos["temperatura_c"].interpolate(method="time").ffill().bfill()
        )
        print(
            "Valores de temperatura tratados por interpolacion: "
            f"{faltantes_temperatura}"
        )

    if datos[["demanda_mwh", "temperatura_c"]].isna().any().any():
        raise ValueError("El snapshot conserva valores nulos.")
    if not datos.index.equals(indice_esperado):
        raise ValueError("El indice horario no es regular.")
    return datos.rename_axis("timestamp")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    hoy = date.today()
    parser.add_argument("--inicio", default=(hoy - timedelta(days=93)).isoformat())
    parser.add_argument("--fin", default=(hoy - timedelta(days=4)).isoformat())
    parser.add_argument("--salida", default="datos/xm_demanda.csv")
    args = parser.parse_args()

    datos = construir_snapshot(args.inicio, args.fin)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    datos.to_csv(salida)

    print(f"Filas: {len(datos)}")
    print(f"Rango: {datos.index.min()} a {datos.index.max()}")
    print(f"Nulos por columna:\n{datos.isna().sum()}")
    print(f"Archivo guardado: {salida}")


if __name__ == "__main__":
    main()
