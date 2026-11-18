import os
import subprocess


def ejecutar_comando(comando):
    print(f"$ {' '.join(comando)}")
    subprocess.run(comando, check=True)


print("Actualmente los datos corresponden a la versión V1")
print("Número de líneas en datos/xm_demanda.csv:")
with open("datos/xm_demanda.csv", encoding="utf-8") as archivo:
	print(sum(1 for _ in archivo))
# tamaño del archivo en bytes
tamaño_archivo = os.path.getsize("datos/xm_demanda.csv")
print(f"Tamaño del archivo: {tamaño_archivo} bytes")
ejecutar_comando(["cat", "datos/xm_demanda.csv.dvc"])
## Rollback a la versión V3
print("Para realizar el ejecicio de volver a la version V3 ejecuto el siguiente comando:")
print("1. Listar todos los commits disponibles del archivo datos/xm_demanda.csv.dvc")
ejecutar_comando(["git", "log", "--oneline", "datos/xm_demanda.csv.dvc"])
print("2. Verifico diferencias entre ambas versiones")
print("Cambios de 9ef2c5e a 8cfd82c:")
ejecutar_comando([
    "dvc", "diff", "9ef2c5e", "8cfd82c",
    "--targets", "datos/xm_demanda.csv", "--json", "--show-hash",
])

print("3. Seleccionar el commit deseado para la version V3 y restaurar el archivo datos/xm_demanda.csv.dvc a esa versión")
ejecutar_comando([
    "git", "checkout", "8cfd82c", "--", "datos/xm_demanda.csv.dvc",
])

print("4. Restaurar el archivo datos/xm_demanda.csv a la versión V3")
ejecutar_comando(["dvc", "checkout", "datos/xm_demanda.csv"])

print("5. Verificar que el archivo datos/xm_demanda.csv ha sido restaurado a la versión V3")
print("Número de líneas en datos/xm_demanda.csv:")
with open("datos/xm_demanda.csv", encoding="utf-8") as archivo:
    print(sum(1 for _ in archivo))
# tamaño del archivo en bytes
tamaño_archivo_2 = os.path.getsize("datos/xm_demanda.csv")
print(f"Tamaño del archivo: {tamaño_archivo_2} bytes")
print('Diferencia de bytes entre la versión V1 y la versión V3:', tamaño_archivo_2 - tamaño_archivo)


print("6. Verificar que datos/xm_demanda.csv.dvc ha sido actualizado a la versión V3")
ejecutar_comando(["cat", "datos/xm_demanda.csv.dvc"])

print("7. Verificar cambios en el archivo datos/xm_demanda.csv.dvc")
ejecutar_comando(["git", "status"])
print("No haré un nuevo commit porque el archivo datos/xm_demanda.csv.dvc ya está en la versión V3 y no hay cambios pendientes.")
