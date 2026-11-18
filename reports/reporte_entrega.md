## Varias versiones de los datos
Se generan varias versiones de los datos:
![alt text](image.png)
## Rollback a versión deseada de los datos
Se configura un script que permite regresar a la versión de los datos de diferentes formas.
1. Como me encontraba en la versión V3, usé el script para volver a los datos de V1.
Previsualizar una restauración:

```bash
.venv/bin/python -m codigo.rollback_version v1
```

Restaurar una versión:

```bash
.venv/bin/python -m codigo.rollback_version v1 --confirmar
```
2. Configuré manualmente los comandos a ejecutar para hacer rollback a la versión V3. Resultado de la ejecución:
![alt text](image-1.png)
![alt text](image-2.png)

## EDA
Se realiza análisis de la V3 de los datos.

### Serie temporal
La gráfica muestra la evolución horaria de la demanda y la temperatura en la versión V3.

![Serie temporal de demanda y temperatura](serie_temporal.png)

### Distribuciones
Los histogramas permiten observar la forma y frecuencia de los valores de demanda y temperatura.

![Distribuciones de las variables](distribuciones.png)

### Diagramas de caja
Los diagramas de caja ayudan a identificar visualmente los posibles valores atípicos de cada variable.

![Diagramas de caja de las variables](diagramas_caja.png)
