# Reporte de calidad y EDA

- Archivo analizado: `datos/xm_demanda.csv`
- Observaciones: **2208**
- Rango: **2026-08-15 00:00:00** a **2026-11-14 23:00:00**
- Índice ordenado ascendentemente: **True**
- Timestamps duplicados: **0**
- Huecos horarios: **0**
- Valores nulos totales: **0**

## Valores atípicos (regla IQR)

| Variable | Cantidad | Porcentaje | Límite inferior | Límite superior |
|---|---:|---:|---:|---:|
| demanda_mwh | 48 | 2.17% | 6199.433 | 14431.876 |
| temperatura_c | 0 | 0.00% | 4.550 | 26.550 |

## Evidencias gráficas

- `serie_temporal.png`: evolución de las variables.
- `distribuciones.png`: histogramas.
- `diagramas_caja.png`: revisión visual de posibles atípicos.

Los detalles se encuentran en los archivos CSV de esta carpeta.
