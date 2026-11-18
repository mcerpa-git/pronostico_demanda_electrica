# Pronóstico de demanda eléctrica

Repositorio para el Taller Semana 1 de pronóstico de demanda eléctrica con
datos de XM, temperatura de Open-Meteo, DVC y MLflow.

## Requisitos

- Python 3.10 o superior.
- Git y DVC configurados.
- Entorno virtual en `.venv`.
- Dependencias de `dependencias.txt`.

Instalar las dependencias:

```bash
.venv/bin/pip install -r dependencias.txt
```

Los comandos siguientes deben ejecutarse desde la raíz del repositorio.

## Flujo general

```text
1. Ingesta XM + Open-Meteo
   ↓
2. CSV en datos/xm_demanda.csv
   ↓
3. Validaciones y reporte EDA
   ↓
4. Versionamiento con DVC
   ↓
5. Comparación y rollback entre versiones
```

## Scripts disponibles

### `codigo/ingesta.py`

Consulta la demanda comercial horaria de XM y la temperatura horaria de
Bogotá. Convierte la demanda de kWh a MWh, construye un índice temporal
regular y guarda el resultado.

Ejecutar con fechas explícitas:

```bash
.venv/bin/python -m codigo.ingesta \
  --inicio 2026-09-01 \
  --fin 2026-09-05
```

Ejecutar con los valores predeterminados:

```bash
.venv/bin/python -m codigo.ingesta
```

Argumentos:

| Argumento | Uso | Predeterminado |
|---|---|---|
| `--inicio` | Primera fecha consultada, formato `AAAA-MM-DD`. | Hace 93 días |
| `--fin` | Última fecha consultada, formato `AAAA-MM-DD`. | Hace 4 días |
| `--salida` | Ruta del CSV generado. | `datos/xm_demanda.csv` |

El archivo generado contiene las columnas `timestamp`, `demanda_mwh` y
`temperatura_c`.

### `codigo/verificaciones.py`

Verifica la calidad del CSV y genera una EDA sencilla. Analiza el orden del
índice, duplicados, huecos horarios, nulos, atípicos y estadísticas
descriptivas.

Ejecutar:

```bash
.venv/bin/python -m codigo.verificaciones \
  --entrada datos/xm_demanda.csv \
  --reports reports
```

Argumentos:

| Argumento | Uso | Predeterminado |
|---|---|---|
| `--entrada` | CSV que se va a verificar. | `datos/xm_demanda.csv` |
| `--reports` | Carpeta donde se guardarán los reportes. | `reports` |

El reporte principal es `reports/reporte_calidad_eda.md`. También genera
tablas CSV y las gráficas `serie_temporal.png`, `distribuciones.png` y
`diagramas_caja.png`.

Los atípicos se detectan con la regla IQR: un valor se considera atípico si
queda fuera de `Q1 - 1.5 × IQR` o `Q3 + 1.5 × IQR`. Esta clasificación es
estadística y no elimina automáticamente observaciones.

### `codigo/analisis_sarimax.py`

Genera la evidencia previa para elegir los parámetros de diferenciación y
estacionalidad de SARIMAX. Analiza ACF/PACF, descomposición estacional,
estacionariedad con ADF/KPSS y el perfil promedio por hora.

Ejecutar:

```bash
.venv/bin/python -m codigo.analisis_sarimax \
  --entrada datos/xm_demanda.csv \
  --reports reports \
  --periodo 24
```

Genera `reports/analisis_sarimax.md`,
`reports/pruebas_estacionariedad.csv`,
`reports/perfil_horario.csv`, ACF/PACF, descomposición estacional y perfil
horario. Las gráficas orientan `d`, `D`, `p`, `q`, `P` y `Q`, pero las
configuraciones finales deben compararse con métricas temporales.

## Pipeline reproducible con DVC

La configuración del pipeline está en `dvc.yaml` y sus parámetros controlables
en `params.yaml`.

```text
datos/xm_demanda.csv
        |
        v
prepare
        |
        +-- datos/train.csv
        +-- datos/test.csv
                |
                v
              train
                |
                v
            metrics.json
```

### Etapa `prepare`

[`codigo/prepare.py`](codigo/prepare.py) lee el snapshot y separa la serie
sin mezclar fechas:

- `datos/train.csv`: observaciones utilizadas por el modelo.
- `datos/test.csv`: últimas horas reservadas para evaluación.

Los parámetros que controlan el corte son:

| Parámetro | Uso | Valor actual |
|---|---|---|
| `prepare.dias_entrenamiento` | Número de días del entrenamiento. | `88` |
| `prepare.horas_prueba` | Horas reservadas al final para prueba. | `48` |

También contiene un control que verifica duplicados y regularidad del índice
horario antes de escribir los CSV.

### Etapa `train`

[`codigo/baseline.py`](codigo/baseline.py) implementa el baseline naive
estacional de 24 horas:

```text
predicción(t) = demanda(t - 24 horas)
```

Calcula:

- `rmse`: raíz del error cuadrático medio.
- `mae`: error absoluto medio.

Las métricas se guardan en `metrics.json` y no se almacenan en caché porque
DVC las registra como métricas modificables.

El pipeline registra además estos parámetros de preparación para SARIMAX:

| Parámetro | Uso | Valor actual |
|---|---|---|
| `model.order` | Orden no estacional `(p,d,q)`. | `[2,1,0]` |
| `model.seasonal_order` | Orden estacional `(P,D,Q,s)`. | `[1,1,1,24]` |
| `model.usar_exogena` | Indica si se usará temperatura. | `false` |

Estos parámetros pertenecen al diseño de modelos posteriores. El baseline
actual todavía no utiliza SARIMAX ni la temperatura exógena.

### Ejecución y reproducibilidad

Ver el grafo:

```bash
.venv/bin/dvc dag
```

Ejecutar o reproducir el pipeline:

```bash
.venv/bin/dvc repro
```

Comprobar si hay cambios pendientes:

```bash
.venv/bin/dvc status
```

Consultar las métricas:

```bash
cat metrics.json
```

El estado completo de la ejecución se guarda en `dvc.lock`. DVC compara
dependencias, parámetros y salidas para decidir qué etapa recalcular:

- Sin cambios, `prepare` y `train` se omiten.
- Cambiar `prepare.horas_prueba` recalcula `prepare` y, debido a sus archivos
  de salida, también `train`.
- Cambiar `model.order` recalcula `train`, pero no `prepare`.
- Cambiar `datos/xm_demanda.csv` recalcula el pipeline desde `prepare`.

Después de reproducir el pipeline, agregar su configuración y lock al historial:

```bash
git add params.yaml dvc.yaml dvc.lock
git commit -m "pipeline: prepara datos y agrega baseline estacional"
```

### `codigo/verificar_versionamiento.py`

Compara automáticamente varios commits que hayan modificado el descriptor
DVC `datos/xm_demanda.csv.dvc`. El argumento indica cuántos commits recientes
se deben revisar.

Ejemplo:

```bash
.venv/bin/python -m codigo.verificar_versionamiento 2
```

También admite rutas personalizadas:

```bash
.venv/bin/python -m codigo.verificar_versionamiento 3 \
  --datos datos/xm_demanda.csv \
  --descriptor datos/xm_demanda.csv.dvc
```

El reporte muestra:

- Hash MD5 y tamaño de cada snapshot.
- Número de observaciones.
- Rango de fechas.
- Variaciones de tamaño y filas.
- Si el contenido cambió.
- Resultado de `dvc diff`.

Si solo existe un commit, el script muestra la versión disponible y explica
que no puede hacer comparaciones.

### `codigo/rollback_version.py`

Permite listar las versiones DVC disponibles y volver a cualquiera de ellas.
Las versiones se identifican como `v1`, `v2`, `v3`, etc., según su historial
cronológico, o mediante un hash de commit.

Listar versiones:

```bash
.venv/bin/python -m codigo.rollback_version --listar
```

Previsualizar una restauración:

```bash
.venv/bin/python -m codigo.rollback_version v1
```

Restaurar una versión:

```bash
.venv/bin/python -m codigo.rollback_version v1 --confirmar
```

Restaurar por hash:

```bash
.venv/bin/python -m codigo.rollback_version 9ef2c5e1 --confirmar
```

Descartar cambios locales y aplicar directamente el rollback:

```bash
.venv/bin/python -m codigo.rollback_version v1 --descartar-cambios
```

Sin `--confirmar`, el script solo muestra la versión seleccionada y no cambia
los datos. Con `--confirmar`, actualiza el descriptor DVC y ejecuta
`dvc pull` y `dvc checkout`. Después verifica que el MD5 real del CSV coincide
con el descriptor y que DVC considera el archivo actualizado. No crea
automáticamente un commit de Git.

Con `--descartar-cambios`, el script descarta primero cualquier modificación
local de `datos/xm_demanda.csv.dvc` y del CSV. Esta bandera implica la
aplicación del rollback; no es necesario combinarla con `--confirmar`.

Opciones adicionales:

| Argumento | Uso | Predeterminado |
|---|---|---|
| `--listar` | Lista las versiones disponibles. | Desactivado |
| `--confirmar` | Aplica la restauración. | Desactivado |
| `--descartar-cambios` | Descarta cambios locales y aplica el rollback. | Desactivado |
| `--datos` | Archivo DVC que se va a restaurar. | `datos/xm_demanda.csv` |
| `--descriptor` | Descriptor DVC asociado. | `datos/xm_demanda.csv.dvc` |

## Evidencias de DVC

Después de actualizar el CSV, crear una nueva versión:

```bash
dvc add datos/xm_demanda.csv
git add datos/xm_demanda.csv.dvc
git commit -m "data: snapshot vN de XM"
dvc push
```

Los hashes MD5 deben anotarse en `NOTAS.md`. Los archivos `reports/` pueden
versionarse en Git porque contienen el resumen y las evidencias gráficas;
los datos grandes permanecen fuera de Git y se administran con DVC.
