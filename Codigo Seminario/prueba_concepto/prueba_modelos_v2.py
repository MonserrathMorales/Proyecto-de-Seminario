"""Prueba de concepto v2: desempeño de modelos locales en la tarea del agente Analista.

Mide, por cada llamada al modelo: tiempos (carga, lectura del prompt, generación), velocidad,
exactitud por campo frente a una respuesta esperada, memoria del modelo (GPU y RAM según Ollama),
RAM del sistema y de los procesos de Ollama, memoria y uso de la GPU (nvidia-smi) y temperatura.

Uso (entorno virtual activado, Ollama abierto, cargador conectado):
    python prueba_modelos_v2.py --escenario aislado
    python prueba_modelos_v2.py --escenario con_juice_shop --modelos gemma4:e4b

Genera en la carpeta resultados/:
    detalle_<escenario>_<fecha>.csv   una fila por llamada al modelo
    resumen_<escenario>_<fecha>.csv   una fila por configuración (modelo y modo de razonamiento)
    entorno_<escenario>_<fecha>.json  hardware, versiones y parámetros de la corrida
"""
import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Literal

import psutil
import requests
from ollama import ResponseError, chat, generate, ps, show
from pydantic import BaseModel, ValidationError

CARPETA = Path(__file__).parent
ARCHIVO_CASOS = os.environ.get("CASOS", "casos_analista.json")  # p. ej. $env:CASOS="casos_juice.json"
CASOS = json.loads((CARPETA / ARCHIVO_CASOS).read_text(encoding="utf-8"))
OLLAMA_URL = "http://localhost:11434"

# Configuraciones a comparar: (modelo, modo de razonamiento activado)
CONFIGURACIONES = [
    ("gemma4:e4b", False),
    ("qwen3.5:9b", False),
    ("qwen3.5:4b", False),
    # ("qwen3.5:4b", True),  # opcional: Qwen3.5-4B con razonamiento (más lento)
]
OPCIONES = {"temperature": 0, "seed": 42, "num_ctx": 4096}
GB = 1024 ** 3


# ---------- Formato obligatorio de la respuesta (lo impone Ollama) ----------
class Clasificacion(BaseModel):
    contiene_identificador: bool
    parametro: str | None
    valor: str | None
    ubicacion: Literal["ruta", "consulta", "cuerpo", "ninguna"]
    visibilidad: Literal["privado", "publico", "no_aplica"]
    cuenta_duena: Literal["A", "B", "ninguna", "desconocida"]
    justificacion: str


CAMPOS_EVALUADOS = ["contiene_identificador", "valor", "ubicacion", "visibilidad", "cuenta_duena"]

SISTEMA = f"""Eres el agente Analista de un sistema que busca fallas de control de acceso (IDOR/BOLA).
Recibes una petición HTTP y su respuesta, y debes indicar si la petición contiene un identificador de objeto.

Definiciones:
- Identificador de objeto: valor que selecciona un registro concreto (pedido, documento, carrito, dirección, usuario).
  Los parámetros de paginación, orden, filtros, moneda o cantidad NO son identificadores.
- parametro: nombre del parámetro (por ejemplo "id" o "direccion_id"); valor: su valor exacto como texto.
- ubicacion: "ruta" si va en el camino de la URL, "consulta" si va después de '?', "cuerpo" si va en el cuerpo, "ninguna" si no hay.
- visibilidad: "privado" si el objeto pertenece a un usuario, "publico" si cualquiera puede verlo (catálogo), "no_aplica" si no hay objeto.
- cuenta_duena: "A" o "B" según a quién pertenece el objeto (deducido de ids o correos en la respuesta),
  "ninguna" si es público o no hay objeto, "desconocida" si no se puede saber.

Usuarios del sistema: A (id {CASOS['usuarios']['A']['id']}, {CASOS['usuarios']['A']['correo']}) y B (id {CASOS['usuarios']['B']['id']}, {CASOS['usuarios']['B']['correo']}).
Responde solo con un JSON que cumpla este esquema: {json.dumps(Clasificacion.model_json_schema(), ensure_ascii=False)}"""


def mensaje_caso(caso: dict) -> str:
    return f"Sesión actual: usuario {caso['sesion']}\nPetición: {caso['peticion']}\nRespuesta: {caso['respuesta']}"


# ---------- Monitoreo de hardware ----------
def nvidia_smi() -> dict:
    """Memoria usada/total de la GPU (MB), uso (%) y temperatura (°C). Vacío si no hay nvidia-smi."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,name,driver_version",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
        usada, total, uso, temp, nombre, driver = [x.strip() for x in out.split(",")]
        return {"vram_usada_mb": float(usada), "vram_total_mb": float(total), "gpu_uso_pct": float(uso),
                "gpu_temp_c": float(temp), "gpu_nombre": nombre, "driver": driver}
    except Exception:
        return {}


def ram_ollama_gb() -> float:
    """Suma de la memoria (working set) de los procesos de Ollama, incluido el proceso que ejecuta el modelo."""
    total = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        nombre = (p.info["name"] or "").lower()
        if nombre.startswith("ollama") and "app" not in nombre:
            try:
                total += p.info["memory_info"].rss
            except Exception:
                pass
    return total / GB


class Monitor:
    """Registra los valores máximos de memoria y GPU mientras el modelo responde (muestreo cada 0,5 s)."""

    def __init__(self):
        self.max = {}
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def _registrar(self, clave, valor):
        if valor is not None:
            self.max[clave] = max(self.max.get(clave, valor), valor)

    def _muestra(self):
        vm = psutil.virtual_memory()
        self._registrar("ram_sistema_max_gb", (vm.total - vm.available) / GB)
        self._registrar("ram_sistema_max_pct", vm.percent)
        self._registrar("ram_ollama_max_gb", ram_ollama_gb())
        g = nvidia_smi()
        self._registrar("vram_usada_max_gb", g.get("vram_usada_mb", 0) / 1024 if g else None)
        self._registrar("gpu_uso_max_pct", g.get("gpu_uso_pct"))
        self._registrar("gpu_temp_max_c", g.get("gpu_temp_c"))

    def _bucle(self):
        while not self._parar.is_set():
            self._muestra()
            self._parar.wait(0.5)

    def __enter__(self):
        self._hilo.start()
        return self

    def __exit__(self, *exc):
        self._parar.set()
        self._hilo.join()
        self._muestra()


# ---------- Evaluación ----------
def normalizar(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    v = str(v).strip().strip('"').lower()
    return v or None


def evaluar(c: Clasificacion, esperado: dict) -> tuple[int, list]:
    fallidos = []
    for campo in CAMPOS_EVALUADOS:
        obtenido, correcto = getattr(c, campo), esperado[campo]
        if campo == "valor" and not esperado["contiene_identificador"]:
            ok = normalizar(obtenido) is None  # sin identificador, el valor debe ir vacío
        else:
            ok = normalizar(obtenido) == normalizar(correcto)
        if not ok:
            fallidos.append(f"{campo}={obtenido!r} (esperado {correcto!r})")
    return len(CAMPOS_EVALUADOS) - len(fallidos), fallidos


# ---------- Información del modelo y del entorno ----------
def info_modelo(modelo: str) -> dict:
    try:
        s = show(modelo)
        d = s.details
        ctx_max = next((v for k, v in (s.modelinfo or {}).items() if k.endswith("context_length")), None)
        return {"familia": d.family, "parametros": d.parameter_size, "cuantizacion": d.quantization_level,
                "contexto_maximo": ctx_max}
    except ResponseError as e:
        return {"error_modelo": str(e)}


def estado_ps(modelo: str) -> dict:
    for m in ps().models:
        if m.model.startswith(modelo) or m.name.startswith(modelo):
            size, vram = m.size or 0, m.size_vram or 0
            return {"modelo_mem_total_gb": round(size / GB, 2), "modelo_mem_gpu_gb": round(vram / GB, 2),
                    "modelo_mem_ram_gb": round((size - vram) / GB, 2),
                    "pct_en_gpu": round(100 * vram / size, 1) if size else None,
                    "contexto_cargado": m.context_length}
    return {}


def en_corriente():
    b = psutil.sensors_battery()
    return None if b is None else b.power_plugged


def entorno(args) -> dict:
    try:
        ollama_v = requests.get(f"{OLLAMA_URL}/api/version", timeout=5).json().get("version")
    except Exception:
        ollama_v = None
    vm = psutil.virtual_memory()
    paquetes = {}
    for p in ["ollama", "pydantic", "psutil", "requests"]:
        try:
            paquetes[p] = pkg_version(p)
        except Exception:
            paquetes[p] = None
    return {
        "fecha": datetime.now().isoformat(timespec="seconds"), "escenario": args.escenario,
        "sistema_operativo": platform.platform(), "procesador": platform.processor(),
        "nucleos_fisicos": psutil.cpu_count(logical=False), "nucleos_logicos": psutil.cpu_count(),
        "ram_total_gb": round(vm.total / GB, 1), "ram_usada_inicio_gb": round((vm.total - vm.available) / GB, 2),
        "gpu": nvidia_smi(), "en_corriente": en_corriente(), "version_ollama": ollama_v,
        "python": sys.version.split()[0], "paquetes": paquetes, "opciones_modelo": OPCIONES,
        "repeticiones": args.repeticiones, "archivo_casos": ARCHIVO_CASOS, "casos": [c["id"] for c in CASOS["casos"]],
        "configuraciones": [{"modelo": m, "razonamiento": t, **info_modelo(m)} for m, t in args.configs],
    }


# ---------- Prueba ----------
def probar(modelo: str, razonamiento: bool, args, filas: list):
    etiqueta = f"{modelo} ({'con' if razonamiento else 'sin'} razonamiento)"
    print(f"\n=== {etiqueta} ===")
    meta = info_modelo(modelo)
    if "error_modelo" in meta:
        print(f"  No se pudo usar {modelo}: {meta['error_modelo']}. Si no está descargado: ollama pull {modelo}")
        return
    generate(model=modelo, prompt="", keep_alive=0)  # asegura que parte descargado
    time.sleep(2)
    vm = psutil.virtual_memory()
    ram_base = (vm.total - vm.available) / GB
    vram_base = nvidia_smi().get("vram_usada_mb", 0) / 1024

    t0 = time.perf_counter()
    with Monitor() as mon_carga:
        generate(model=modelo, prompt="", keep_alive="10m", options=OPCIONES)  # carga el modelo sin generar texto
    carga_s = time.perf_counter() - t0
    mem = estado_ps(modelo)
    print(f"  Carga: {carga_s:.1f} s | memoria del modelo: {mem.get('modelo_mem_total_gb')} GB "
          f"({mem.get('pct_en_gpu')}% en GPU) | RAM sistema: {mon_carga.max.get('ram_sistema_max_pct')}%")

    for rep in range(1, args.repeticiones + 1):
        for caso in CASOS["casos"]:
            fila = {"fecha_hora": datetime.now().isoformat(timespec="seconds"), "escenario": args.escenario,
                    "modelo": modelo, "razonamiento": razonamiento, **meta, "num_ctx": OPCIONES["num_ctx"],
                    "caso": caso["id"], "repeticion": rep, "carga_inicial_s": round(carga_s, 2),
                    "ram_sistema_base_gb": round(ram_base, 2), "vram_base_gb": round(vram_base, 2),
                    "en_corriente": en_corriente()}
            t = time.perf_counter()
            try:
                with Monitor() as mon:
                    r = chat(model=modelo, think=razonamiento, format=Clasificacion.model_json_schema(),
                             options=OPCIONES, keep_alive="10m",
                             messages=[{"role": "system", "content": SISTEMA},
                                       {"role": "user", "content": mensaje_caso(caso)}])
            except ResponseError as e:
                print(f"  {caso['id']} rep {rep}: error de Ollama: {e}")
                fila.update({"error": str(e)})
                filas.append(fila)
                continue
            total = time.perf_counter() - t
            ns = 1e9
            prompt_s = (r.prompt_eval_duration or 0) / ns
            gen_s = (r.eval_duration or 0) / ns
            try:
                c = Clasificacion.model_validate_json(r.message.content)
                valido = True
                aciertos, fallidos = evaluar(c, caso["esperado"])
            except ValidationError as e:
                valido, aciertos, fallidos = False, 0, [f"JSON inválido: {e.errors()[0]['msg']}"]
            fila.update({
                "tiempo_total_s": round(total, 2), "tokens_prompt": r.prompt_eval_count, "lectura_prompt_s": round(prompt_s, 2),
                "tokens_salida": r.eval_count, "generacion_s": round(gen_s, 2),
                "tokens_por_s_prompt": round(r.prompt_eval_count / prompt_s, 1) if prompt_s else None,
                "tokens_por_s_salida": round(r.eval_count / gen_s, 1) if gen_s else None,
                "tokens_razonamiento_aprox": len((r.message.thinking or "").split()) if razonamiento else 0,
                "json_valido": valido, "aciertos_campos": aciertos, "total_campos": len(CAMPOS_EVALUADOS),
                "correcta": aciertos == len(CAMPOS_EVALUADOS), "campos_fallidos": " | ".join(fallidos),
                **estado_ps(modelo), **{k: round(v, 2) for k, v in mon.max.items()},
                "respuesta": r.message.content,
            })
            filas.append(fila)
            print(f"  {caso['id']:<24} rep {rep}: {total:5.1f} s | {fila['tokens_por_s_salida']} tok/s | "
                  f"campos {aciertos}/{len(CAMPOS_EVALUADOS)} | RAM {mon.max.get('ram_sistema_max_pct')}% | "
                  f"VRAM {mon.max.get('vram_usada_max_gb', 0):.2f} GB")
    generate(model=modelo, prompt="", keep_alive=0)  # libera la memoria antes del siguiente modelo
    time.sleep(3)


def resumir(filas: list) -> list:
    resumen = []
    claves = sorted({(f["modelo"], f["razonamiento"]) for f in filas})
    for modelo, razonamiento in claves:
        fs = [f for f in filas if f["modelo"] == modelo and f["razonamiento"] == razonamiento and "tiempo_total_s" in f]
        if not fs:
            continue

        def col(k):
            return [f[k] for f in fs if f.get(k) is not None]

        def media(k):
            v = col(k)
            return round(statistics.mean(v), 2) if v else None

        def desv(k):
            v = col(k)
            return round(statistics.stdev(v), 2) if len(v) > 1 else None

        def maximo(k):
            v = col(k)
            return round(max(v), 2) if v else None

        resumen.append({
            "modelo": modelo, "razonamiento": razonamiento, "parametros": fs[0].get("parametros"),
            "cuantizacion": fs[0].get("cuantizacion"), "llamadas": len(fs),
            "exactitud_pct": round(100 * sum(f["correcta"] for f in fs) / len(fs), 1),
            "aciertos_campos_pct": round(100 * sum(f["aciertos_campos"] for f in fs) / (len(fs) * len(CAMPOS_EVALUADOS)), 1),
            "json_valido_pct": round(100 * sum(f["json_valido"] for f in fs) / len(fs), 1),
            "tiempo_medio_s": media("tiempo_total_s"), "tiempo_desv_s": desv("tiempo_total_s"),
            "tokens_por_s_salida_media": media("tokens_por_s_salida"), "tokens_por_s_salida_desv": desv("tokens_por_s_salida"),
            "carga_inicial_s": fs[0].get("carga_inicial_s"), "modelo_mem_total_gb": fs[0].get("modelo_mem_total_gb"),
            "modelo_mem_gpu_gb": fs[0].get("modelo_mem_gpu_gb"), "pct_en_gpu": fs[0].get("pct_en_gpu"),
            "ram_sistema_max_gb": maximo("ram_sistema_max_gb"), "ram_sistema_max_pct": maximo("ram_sistema_max_pct"),
            "ram_ollama_max_gb": maximo("ram_ollama_max_gb"), "vram_usada_max_gb": maximo("vram_usada_max_gb"),
            "gpu_temp_max_c": maximo("gpu_temp_max_c"),
            "casos_fallidos": ", ".join(sorted({f["caso"] for f in fs if not f["correcta"]})),
        })
    return resumen


def guardar_csv(ruta: Path, filas: list):
    columnas = []
    for f in filas:
        columnas += [k for k in f if k not in columnas]
    with ruta.open("w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig: Excel muestra bien los acentos
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--escenario", default="aislado", help="etiqueta de la corrida, p. ej. aislado o con_juice_shop")
    ap.add_argument("--modelos", nargs="*", help="limita la prueba a estos modelos")
    ap.add_argument("--repeticiones", type=int, default=3)
    args = ap.parse_args()
    args.configs = [c for c in CONFIGURACIONES if not args.modelos or c[0] in args.modelos]

    if en_corriente() is False:
        print("AVISO: el equipo no está conectado al cargador; los tiempos pueden empeorar.")
    if not nvidia_smi():
        print("AVISO: no se encontró nvidia-smi; no se registrará la memoria de la GPU.")

    sello = datetime.now().strftime("%Y%m%d_%H%M")
    salida = CARPETA / "resultados"
    salida.mkdir(exist_ok=True)
    (salida / f"entorno_{args.escenario}_{sello}.json").write_text(
        json.dumps(entorno(args), ensure_ascii=False, indent=2), encoding="utf-8")

    filas = []
    inicio = time.perf_counter()
    for modelo, razonamiento in args.configs:
        probar(modelo, razonamiento, args, filas)
    guardar_csv(salida / f"detalle_{args.escenario}_{sello}.csv", filas)
    resumen = resumir(filas)
    guardar_csv(salida / f"resumen_{args.escenario}_{sello}.csv", resumen)

    print(f"\nDuración total: {(time.perf_counter() - inicio) / 60:.1f} min")
    print(f"{'Modelo':<28}{'Exactitud':>10}{'Campos':>8}{'Tiempo':>9}{'tok/s':>8}{'GPU%':>7}{'RAM máx':>9}")
    for r in resumen:
        nombre = r["modelo"] + (" +raz" if r["razonamiento"] else "")
        print(f"{nombre:<28}{r['exactitud_pct']:>9}%{r['aciertos_campos_pct']:>7}%{r['tiempo_medio_s']:>8}s"
              f"{r['tokens_por_s_salida_media']:>8}{r['pct_en_gpu'] or 0:>7}{r['ram_sistema_max_pct']:>8}%")
    print(f"\nArchivos guardados en {salida}")


if __name__ == "__main__":
    main()
