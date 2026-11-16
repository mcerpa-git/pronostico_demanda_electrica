# Reporte de calidad y EDA

- Archivo analizado: `datos/xm_demanda.csv`
- Observaciones: **2184**
- Rango: **2026-08-15 00:00:00** a **2026-11-13 23:00:00**
- Índice ordenado ascendentemente: **True**
- Timestamps duplicados: **0**
- Huecos horarios: **0**
- Valores nulos totales: **0**

## Valores atípicos (regla IQR)

| Variable | Cantidad | Porcentaje | Límite inferior | Límite superior |
|---|---:|---:|---:|---:|
| demanda_mwh | 48 | 2.20% | 6187.470 | 14421.893 |
| temperatura_c | 0 | 0.00% | 4.800 | 26.400 |

## Evidencias gráficas

- `serie_temporal.png`: evolución de las variables.
- `distribuciones.png`: histogramas.
- `diagramas_caja.png`: revisión visual de posibles atípicos.

Los detalles se encuentran en los archivos CSV de esta carpeta.
