"""Prueba de concepto 1: velocidad, memoria y salida JSON de los modelos locales en Ollama.

Uso (con el entorno virtual activado y Ollama abierto):
    python prueba_modelos.py
Genera resultados_modelos.csv en esta misma carpeta.
"""
import csv
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

from ollama import ResponseError, chat
from pydantic import BaseModel, ValidationError

MODELOS = ["qwen3.5:4b", "qwen3.5:9b", "gemma4:e4b"]
REPETICIONES = 5
SALIDA = Path(__file__).with_name("resultados_modelos.csv")


class Clasificacion(BaseModel):
    parametro: str | None
    es_identificador_de_objeto: bool
    cuenta_duena: str | None
    justificacion: str


PROMPT = """Eres el agente Analista de un sistema que busca fallas IDOR/BOLA.
Sesión actual: usuario A (id 17).
Petición: GET /api/pedidos/1043?moneda=CLP
Respuesta (200): {"id": 1043, "cliente_id": 17, "direccion": "Calle Canario-A-7F3", "total": 15990}
Indica si la petición contiene un parámetro que identifica un objeto, cuál es y a qué cuenta pertenece el objeto.
Responde solo con JSON según este esquema: """ + str(Clasificacion.model_json_schema())


def estado_ollama(modelo: str) -> str:
    """Devuelve la línea de 'ollama ps' del modelo (tamaño en memoria y reparto CPU/GPU)."""
    salida = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    for linea in salida.splitlines():
        if linea.startswith(modelo):
            return " ".join(linea.split()[2:])
    return "no cargado"


def es_correcta(c: Clasificacion) -> bool:
    texto = f"{c.parametro} {c.cuenta_duena}".lower()
    return c.es_identificador_de_objeto and "1043" in texto and ("17" in texto or " a" in f" {texto}")


def probar(modelo: str, filas: list) -> None:
    print(f"\n=== {modelo} ===")
    t0 = time.perf_counter()
    try:  # primera llamada: incluye la carga del modelo en memoria
        chat(model=modelo, messages=[{"role": "user", "content": "Hola"}], think=False)
    except ResponseError as e:
        print(f"  No se pudo cargar: {e}")
        return
    print(f"  Carga inicial: {time.perf_counter() - t0:.1f} s | ollama ps: {estado_ollama(modelo)}")
    velocidades = []
    for i in range(1, REPETICIONES + 1):
        t = time.perf_counter()
        try:
            r = chat(model=modelo, messages=[{"role": "user", "content": PROMPT}],
                     format=Clasificacion.model_json_schema(), options={"temperature": 0}, think=False)
        except ResponseError as e:
            print(f"  Repetición {i}: error {e}")
            continue
        total = time.perf_counter() - t
        tps = r.eval_count / (r.eval_duration / 1e9) if r.eval_duration else 0
        try:
            c = Clasificacion.model_validate_json(r.message.content)
            valido, correcto = True, es_correcta(c)
        except ValidationError:
            valido, correcto = False, False
        velocidades.append(tps)
        print(f"  Repetición {i}: {total:5.1f} s | {tps:5.1f} tokens/s | JSON válido: {valido} | correcta: {correcto}")
        filas.append([datetime.now().isoformat(timespec="seconds"), modelo, i, round(total, 2),
                      r.eval_count, round(tps, 1), valido, correcto, estado_ollama(modelo)])
    if velocidades:
        print(f"  Promedio: {statistics.mean(velocidades):.1f} tokens/s")
    subprocess.run(["ollama", "stop", modelo], capture_output=True)  # libera la memoria


if __name__ == "__main__":
    filas = []
    for m in MODELOS:
        probar(m, filas)
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "modelo", "repeticion", "segundos", "tokens_salida", "tokens_por_segundo",
                    "json_valido", "respuesta_correcta", "ollama_ps"])
        w.writerows(filas)
    print(f"\nResultados guardados en {SALIDA}")
