"""Crea una reproducción aislada a partir de un run ID de MLflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import mlflow
import yaml


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]


def ejecutar(
    comando: list[str],
    carpeta: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        comando,
        cwd=carpeta or RAIZ_REPOSITORIO,
        text=True,
        capture_output=True,
        check=False,
    )


def exigir(comando: list[str], error: str, carpeta: Path | None = None) -> str:
    resultado = ejecutar(comando, carpeta)
    if resultado.returncode != 0:
        detalle = resultado.stderr.strip() or resultado.stdout.strip()
        raise RuntimeError(f"{error}\n{detalle}")
    return resultado.stdout


def contenido_git(commit: str, ruta: str) -> str:
    return exigir(
        ["git", "--no-pager", "show", f"{commit}:{ruta}"],
        f"No se pudo leer {ruta} en el commit {commit[:8]}.",
    )


def md5_bytes(contenido: bytes) -> str:
    return hashlib.md5(contenido).hexdigest()


def valor_bool(valor: object) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"true", "yes", "1", "si", "sí"}


def cargar_yaml_texto(texto: str) -> dict:
    contenido = yaml.safe_load(texto)
    if not isinstance(contenido, dict):
        raise RuntimeError("El archivo YAML no contiene un objeto válido.")
    return contenido


def buscar_commit_run(
    run_id: str,
    git_commit: str,
    dvc_hash: str,
    run_name: str,
) -> tuple[str, dict, dict, dict]:
    commits = exigir(
        ["git", "rev-list", "--topo-order", "--all"],
        "No se pudo consultar el historial de Git.",
    ).splitlines()

    candidatos: list[tuple[str, dict, dict, dict]] = []
    for commit in commits:
        try:
            params_texto = contenido_git(commit, "params.yaml")
            params = cargar_yaml_texto(params_texto)
            descriptor = cargar_yaml_texto(
                contenido_git(commit, "datos/xm_demanda.csv.dvc")
            )
            lock = cargar_yaml_texto(contenido_git(commit, "dvc.lock"))
        except RuntimeError:
            continue

        outs = descriptor.get("outs")
        stages = lock.get("stages")
        if not isinstance(outs, list) or not outs:
            continue
        if not isinstance(stages, dict) or "train" not in stages:
            continue
        if str(outs[0].get("md5")) != dvc_hash:
            continue

        mlflow_params = params.get("mlflow")
        modelo_params = params.get("model")
        if not isinstance(mlflow_params, dict) or not isinstance(modelo_params, dict):
            continue
        if str(mlflow_params.get("run_name")) != run_name:
            continue

        candidatos.append((commit, params, descriptor, lock))

    if not candidatos:
        raise RuntimeError(
            f"No se encontró un commit reproducible para el run {run_id}. "
            "Verifica git_commit, dvc_data_hash y mlflow.run_name."
        )

    commit_tag_en_historial = [
        candidato for candidato in candidatos
        if candidato[0].startswith(git_commit)
    ]
    if commit_tag_en_historial:
        return commit_tag_en_historial[0]

    return candidatos[0]


def buscar_script_por_lock(lock: dict) -> tuple[str, str] | None:
    train = lock.get("stages", {}).get("train")
    if not isinstance(train, dict):
        return None
    for dependencia in train.get("deps", []):
        if not isinstance(dependencia, dict):
            continue
        if dependencia.get("path") == "codigo/train.py":
            md5_buscado = str(dependencia.get("md5", ""))
            if md5_buscado:
                return md5_buscado, "codigo/train.py"
    return None


def buscar_script_commit(md5_buscado: str) -> str:
    commits = exigir(
        ["git", "rev-list", "--topo-order", "--all"],
        "No se pudo buscar codigo/train.py en el historial.",
    ).splitlines()

    for commit in commits:
        resultado = ejecutar(
            ["git", "--no-pager", "show", f"{commit}:codigo/train.py"]
        )
        if resultado.returncode == 0:
            if md5_bytes(resultado.stdout.encode("utf-8")) == md5_buscado:
                return commit
    raise RuntimeError(
        f"No se encontró en Git una codigo/train.py con MD5 "
        f"{md5_buscado}."
    )


def crear_rama_y_worktree(
    commit: str,
    carpeta: Path,
    rama: str,
) -> None:
    exigir(
        ["git", "worktree", "prune"],
        "No se pudo limpiar worktrees obsoletos.",
    )

    if carpeta.exists():
        raise RuntimeError(
            f"La carpeta destino ya existe: {carpeta}. "
            "Elija otra ruta o elimínela manualmente."
        )

    ramas = exigir(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"],
        "No se pudo listar las ramas.",
    ).splitlines()
    if rama in ramas:
        hash_rama = exigir(
            ["git", "rev-parse", rama],
            f"No se pudo consultar la rama existente '{rama}'.",
        ).strip()
        if hash_rama != commit:
            raise RuntimeError(
                f"La rama '{rama}' existe pero apunta a {hash_rama[:8]}, "
                f"no al commit reproducible {commit[:8]}."
            )
        exigir(
            ["git", "worktree", "add", str(carpeta), rama],
            "No se pudo crear el worktree para la rama existente.",
        )
    else:
        exigir(
            ["git", "worktree", "add", "-b", rama, str(carpeta), commit],
            "No se pudo crear la rama y el worktree.",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea una reproducción segura basada en un run ID de MLflow."
    )
    parser.add_argument("run_id", help="ID completo del run de MLflow.")
    parser.add_argument(
        "--carpeta",
        type=Path,
        help="Ruta externa para el worktree. Predeterminado: carpeta hermana.",
    )
    parser.add_argument(
        "--rama",
        help="Nombre de la rama. Predeterminado: reproduccion/<run_id corto>.",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Crea el worktree y restaura datos; sin esto solo muestra la vista previa.",
    )
    parser.add_argument(
        "--ejecutar",
        action="store_true",
        help="Después de restaurar, ejecuta dvc repro --force train.",
    )
    argumentos = parser.parse_args()

    run_id = argumentos.run_id.strip()
    if not run_id:
        raise RuntimeError("El run ID no puede estar vacío.")

    configuracion_actual = cargar_yaml_texto(
        (RAIZ_REPOSITORIO / "params.yaml").read_text(encoding="utf-8")
    )
    mlflow_config = configuracion_actual.get("mlflow", {})
    if not isinstance(mlflow_config, dict):
        raise RuntimeError("params.yaml no contiene el bloque mlflow válido.")

    mlflow.set_tracking_uri(str(mlflow_config["tracking_uri"]))
    run = mlflow.get_run(run_id)
    tags = run.data.tags
    parametros = run.data.params
    metricas = run.data.metrics

    git_commit_tag = str(tags.get("git_commit", "")).strip()
    dvc_hash = str(tags.get("dvc_data_hash", "")).strip()
    run_name = str(tags.get("mlflow.runName", "")).strip()
    if not git_commit_tag or not dvc_hash:
        raise RuntimeError(
            "El run no contiene tags git_commit y dvc_data_hash."
        )

    commit, params, descriptor, lock = buscar_commit_run(
        run_id,
        git_commit_tag,
        dvc_hash,
        run_name,
    )
    script_lock = buscar_script_por_lock(lock)
    if not script_lock:
        raise RuntimeError("dvc.lock no registra codigo/train.py.")
    md5_script, script_ruta = script_lock
    script_commit = buscar_script_commit(md5_script)

    carpeta = argumentos.carpeta
    if carpeta is None:
        carpeta = RAIZ_REPOSITORIO.parent / (
            f"{RAIZ_REPOSITORIO.name}_reproduccion_{run_id[:8]}"
        )
    carpeta = carpeta.resolve()
    rama = argumentos.rama or f"reproduccion/{run_id[:8]}"

    vista = {
        "run_id": run_id,
        "run_name": run_name,
        "git_commit_run": git_commit_tag,
        "commit_reproducible": commit,
        "script_commit": script_commit,
        "dvc_data_hash": dvc_hash,
        "train_script_md5": md5_script,
        "rama": rama,
        "carpeta": str(carpeta),
        "parametros": parametros,
        "metricas": metricas,
        "params_yaml": params,
    }

    print(json.dumps(vista, indent=2, ensure_ascii=False))
    if not argumentos.confirmar and not argumentos.ejecutar:
        print("\nVista previa: no se modificó el repositorio.")
        print("Ejecute nuevamente con --confirmar para crear el entorno.")
        return

    crear_rama_y_worktree(commit, carpeta, rama)

    texto_script = contenido_git(script_commit, script_ruta)
    (carpeta / script_ruta).write_text(texto_script, encoding="utf-8")

    manifiesto = carpeta / f"reproduccion_{run_id}.json"
    manifiesto.write_text(
        json.dumps(vista, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    entorno_virtual = RAIZ_REPOSITORIO / ".venv"
    destino_entorno = carpeta / ".venv"
    if entorno_virtual.is_dir() and not destino_entorno.exists():
        try:
            destino_entorno.symlink_to(entorno_virtual, target_is_directory=True)
        except OSError:
            pass

    dvc = carpeta / ".venv/bin/dvc"
    if not dvc.is_file():
        dvc = shutil.which("dvc")
        if dvc is None:
            raise RuntimeError("No se encontró el ejecutable de DVC.")
        dvc_comando = dvc
    else:
        dvc_comando = str(dvc)

    exigir(
        [dvc_comando, "pull"],
        "No se pudo descargar los datos con DVC.",
        carpeta,
    )
    exigir(
        [dvc_comando, "checkout", "--force"],
        "No se pudo restaurar los datos con DVC.",
        carpeta,
    )

    archivo_datos = carpeta / "datos/xm_demanda.csv"
    if archivo_datos.is_file():
        md5_real = md5_bytes(archivo_datos.read_bytes())
        if md5_real != dvc_hash:
            raise RuntimeError(
                f"MD5 restaurado incorrecto: esperado={dvc_hash}, "
                f"real={md5_real}"
            )

    mlflow_db = RAIZ_REPOSITORIO / "mlflow.db"
    if mlflow_db.is_file():
        shutil.copy2(mlflow_db, carpeta / "mlflow.db")

    mlruns = RAIZ_REPOSITORIO / "mlruns"
    if mlruns.is_dir():
        destino_mlruns = carpeta / "mlruns"
        if not destino_mlruns.exists():
            shutil.copytree(mlruns, destino_mlruns)

    exigir(
        [dvc_comando, "status"],
        "No se pudo verificar el estado DVC.",
        carpeta,
    )

    print(f"\nEntorno creado en: {carpeta}")
    print(f"Rama creada: {rama}")
    print("Datos restaurados y hash DVC verificado.")

    if argumentos.ejecutar:
        mlflow_db_worktree = carpeta / "mlflow.db"
        mlflow_tracking_uri = f"sqlite:///{mlflow_db_worktree}"
        mlflow.set_tracking_uri(mlflow_tracking_uri)
        exp = mlflow.set_experiment(
            str(params["mlflow"]["experiment_name"])
        )
        antes = set(
            mlflow.search_runs(
                experiment_ids=[exp.experiment_id],
                output_format="pandas",
            ).get("run_id", [])
        )

        exigir(
            [dvc_comando, "repro", "--force", "train"],
            "Falló la reproducción del run.",
            carpeta,
        )

        despues = mlflow.search_runs(
            experiment_ids=[exp.experiment_id],
            output_format="pandas",
        )
        nuevos = [
            str(run_id)
            for run_id in despues.get("run_id", [])
            if str(run_id) not in antes
        ]
        if len(nuevos) != 1:
            raise RuntimeError(
                "La reproducción no produjo exactamente un run nuevo "
                f"(se encontraron {len(nuevos)})."
            )

        nuevo_run_id = nuevos[0]
        nuevo_run = mlflow.get_run(nuevo_run_id)
        diferencia_metricas = {}
        for nombre in sorted(metricas):
            if nombre in nuevo_run.data.metrics:
                diferencia_metricas[nombre] = {
                    "original": float(metricas[nombre]),
                    "nuevo": float(nuevo_run.data.metrics[nombre]),
                    "diferencia": (
                        float(nuevo_run.data.metrics[nombre])
                        - float(metricas[nombre])
                    ),
                }

        vista["nuevo_run_id"] = nuevo_run_id
        vista["nuevo_run_metricas"] = nuevo_run.data.metrics
        vista["comparacion_metricas"] = diferencia_metricas
        manifiesto.write_text(
            json.dumps(vista, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print("\nReproducción finalizada.")
        print(f"Run original restaurado: {run_id}")
        print(f"Run nuevo creado: {nuevo_run_id}")
        print("Comparación de métricas:")
        print(json.dumps(diferencia_metricas, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)