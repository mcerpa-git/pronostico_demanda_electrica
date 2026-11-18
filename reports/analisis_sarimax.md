# Evidencia previa para selección de SARIMAX

- Archivo analizado: `datos/xm_demanda.csv`
- Observaciones originales: **2208**
- Periodo estacional evaluado: **24 horas**
- Rango: **2026-08-15 00:00:00** a **2026-11-14 23:00:00**

## Estacionariedad

| Transformación | ADF p-valor | KPSS p-valor | Ambas indican estacionaria |
|---|---:|---:|:---:|
| original | 0.000019 | 0.010000 | No |
| diferencia_regular | 0.000000 | 0.100000 | Sí |
| diferencia_estacional_24 | 0.000075 | 0.100000 | Sí |
| diferencia_regular_estacional | 0.000000 | 0.100000 | Sí |

Interpretación:
- Serie original estacionaria según ambas pruebas: No.
- Diferencia regular estacionaria según ambas pruebas: Sí.
- Diferencia estacional de 24 horas estacionaria según ambas pruebas: Sí.
- Diferencia regular y estacional estacionaria según ambas pruebas: Sí.

Esta información orienta los valores iniciales de `d`, `D` y el periodo estacional `s=24`, pero no reemplaza la comparación de configuraciones sobre el conjunto de prueba.

## Evidencias gráficas

- `original_acf_pacf.png`: autocorrelación y autocorrelación parcial.
- `diferencia_regular_estacional_acf_pacf.png`: rezagos después de diferencias.
- `descomposicion_estacional.png`: tendencia, estacionalidad y residuos.
- `perfil_horario.png`: demanda promedio por hora del día.

Los valores numéricos están en `pruebas_estacionariedad.csv` y `perfil_horario.csv`.
