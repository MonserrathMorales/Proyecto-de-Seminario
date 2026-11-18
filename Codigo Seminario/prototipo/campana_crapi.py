"""Campaña con OWASP crAPI: repite el flujo completo varias veces y resume los resultados.

Cada repetición ejecuta el grafo explorador -> analista -> validacion -> cerrar con alcance_crapi.json, igual
que probar_crapi.py --grafo. Al terminar, calcula media, desviación estándar, mínimo y máximo de cada medida,
y en cuántas repeticiones aparece cada hallazgo confirmado y cada decisión del modelo.
Necesita crAPI levantado y, en modo reglas_llm, Ollama abierto con gemma4:e4b. Abre el navegador en cada repetición.
Guarda en datos/campana_<fecha>/: campana.json (todo) y corridas.csv (una fila por repetición).
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python campana_crapi.py                                   # 5 repeticiones en modo reglas_llm
    python campana_crapi.py --repeticiones 3 --modo solo_reglas
"""
import csv
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from prototipo import explorador as mod_explorador
from prototipo.grafo import SESIONES, construir
from prototipo.modelos import ResultadoAnalisis, ResultadoValidacion


def argumento(nombre: str, defecto: str) -> str:
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else defecto


REPETICIONES = int(argumento("--repeticiones", "5"))
MODO = argumento("--modo", "reglas_llm")
if MODO not in ("solo_reglas", "reglas_llm"):
    raise SystemExit(f"Modo desconocido: {MODO}. Usa solo_reglas o reglas_llm.")
TOKEN = re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}|eyJ[A-Za-z0-9_-]{8,}")
inicio_campana = datetime.now()
carpeta_campana = mod_explorador.CARPETA_DATOS / f"campana_{inicio_campana:%Y%m%d_%H%M%S}"
carpeta_campana.mkdir(parents=True, exist_ok=True)
print(f"Campaña crAPI: {REPETICIONES} repeticiones en modo {MODO}. Resultados en {carpeta_campana}\n")


def corrida(n: int) -> dict:
    """Ejecuta el grafo una vez y devuelve sus medidas (sin tokens ni datos de las respuestas)."""
    print(f"===== Repetición {n} de {REPETICIONES} ({datetime.now():%H:%M:%S}) =====")
    t0 = time.perf_counter()
    grafo = construir()
    config = {"configurable": {"thread_id": f"campana-{n}"}}
    estado = grafo.invoke({"ruta_alcance": "alcance_crapi.json", "modo_analista": MODO}, config)
    fila = {"repeticion": n, "ejecucion": estado.get("ejecucion", ""), "error": estado.get("error") or "",
            "duracion_total_s": round(time.perf_counter() - t0, 1)}
    for e in estado["registro"]:
        fila[f"duracion_{e['etapa']}_s"] = e["duracion_s"]
        print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>6} s")
    if fila["error"] or "ruta_validacion" not in estado:
        print(f"   ERROR: {fila['error']}\n")
        return {"fila": fila, "confirmados": [], "decisiones_llm": []}

    carpeta = Path(estado["ruta_validacion"]).parent
    a = ResultadoAnalisis.model_validate_json(Path(estado["ruta_analisis"]).read_text(encoding="utf-8"))
    v = ResultadoValidacion.model_validate_json(Path(estado["ruta_validacion"]).read_text(encoding="utf-8"))
    por_id = {h.id: h for h in a.hipotesis}
    exploracion = estado["resumen_exploracion"]
    # Los ids de los reportes cambian en cada repetición: el hallazgo se identifica por tipo, endpoint y quién lee a quién
    confirmados = sorted({f"{x.tipo} {x.endpoint} | {por_id[x.hipotesis].sesion_prueba} lee a "
                          f"{por_id[x.hipotesis].cuenta_duena} ({por_id[x.hipotesis].objeto or '-'})"
                          for x in v.veredictos if x.clase == "confirmado"})
    decisiones = sorted({f"{c.sesion} {c.endpoint} {c.parametro}={c.valor} -> identificador={c.es_identificador}, "
                         f"{c.visibilidad or '-'}, dueña {c.cuenta_duena or '-'}"
                         for c in a.candidatos if c.decidido_por == "llm"})
    reportes = [x for x in v.veredictos if por_id[x.hipotesis].objeto == "reporte"]
    textos = [f.read_text(encoding="utf-8") for f in carpeta.glob("*.json")]
    fila.update({
        "peticiones_conservadas": exploracion["conservadas"], "endpoints": len(a.endpoints),
        "candidatos": len(a.candidatos), "por_inventario": sum(c.decidido_por == "inventario" for c in a.candidatos),
        "decididos_por_llm": sum(c.decidido_por == "llm" for c in a.candidatos), "consultas_llm": a.consultas_llm,
        "hipotesis": len(a.hipotesis), "peticiones_enviadas": v.enviadas,
        "confirmado": v.resumen.get("confirmado", 0), "dudoso": v.resumen.get("dudoso", 0),
        "descartado": v.resumen.get("descartado", 0),
        "bola2_confirmados": sum(x.tipo == "horizontal" and x.clase == "confirmado" for x in reportes),
        "ubicacion_observada": int(any("/location" in e.plantilla for e in a.endpoints)),
        "tokens_en_evidencia": int(any(TOKEN.search(t) for t in textos)),
        "sesiones_liberadas": int(estado["ejecucion"] not in SESIONES)})
    print(f"   candidatos {fila['candidatos']} (inventario {fila['por_inventario']}, LLM {fila['decididos_por_llm']}), "
          f"consultas al modelo {fila['consultas_llm']}, hipótesis {fila['hipotesis']}")
    print(f"   confirmado {fila['confirmado']}, dudoso {fila['dudoso']}, descartado {fila['descartado']}; "
          f"BOLA 2 confirmado en {fila['bola2_confirmados']} direcciones; tokens en la evidencia: "
          f"{'sí' if fila['tokens_en_evidencia'] else 'no'}")
    for d in decisiones:
        print(f"   LLM: {d}")
    print(f"   evidencia en {carpeta}\n")
    return {"fila": fila, "confirmados": confirmados, "decisiones_llm": decisiones}


resultados = []
for n in range(1, REPETICIONES + 1):
    try:
        resultados.append(corrida(n))
    except Exception as e:  # una repetición fallida no detiene la campaña
        print(f"   ERROR inesperado: {type(e).__name__}: {e}\n")
        resultados.append({"fila": {"repeticion": n, "error": f"{type(e).__name__}: {e}"[:300]},
                           "confirmados": [], "decisiones_llm": []})

# ---------- Resumen ----------
filas = [r["fila"] for r in resultados]
validas = [f for f in filas if not f.get("error")]
medidas = ["duracion_total_s", "duracion_explorador_s", "duracion_analista_s", "duracion_validacion_s",
           "peticiones_conservadas", "endpoints", "candidatos", "por_inventario", "decididos_por_llm",
           "consultas_llm", "hipotesis", "peticiones_enviadas", "confirmado", "dudoso", "descartado",
           "bola2_confirmados"]
resumen = {}
for m in medidas:
    valores = [f[m] for f in validas if m in f]
    if valores:
        resumen[m] = {"media": round(statistics.mean(valores), 2),
                      "desviacion": round(statistics.stdev(valores), 2) if len(valores) > 1 else 0.0,
                      "minimo": min(valores), "maximo": max(valores)}


def estabilidad(clave: str) -> dict[str, str]:
    conteo: dict[str, int] = {}
    for r in resultados:
        if not r["fila"].get("error"):
            for x in r[clave]:
                conteo[x] = conteo.get(x, 0) + 1
    return {x: f"{c}/{len(validas)}" for x, c in sorted(conteo.items())}


confirmados, decisiones = estabilidad("confirmados"), estabilidad("decisiones_llm")
print("=" * 100)
print(f"RESUMEN: {len(validas)} de {REPETICIONES} repeticiones completas, modo {MODO}, "
      f"{(datetime.now() - inicio_campana).total_seconds() / 60:.1f} min en total\n")
print(f" {'Medida':<26}{'Media':>10}{'Desv. est.':>12}{'Mín':>9}{'Máx':>9}")
for m, r in resumen.items():
    print(f" {m:<26}{r['media']:>10}{r['desviacion']:>12}{r['minimo']:>9}{r['maximo']:>9}")
print("\n Estabilidad de los hallazgos confirmados (repeticiones en que aparece):")
for x, c in confirmados.items() or {"(ninguno)": ""}.items():
    print(f"   {c:>5}  {x}")
if MODO == "reglas_llm":
    print("\n Estabilidad de las decisiones del modelo:")
    for x, c in decisiones.items() or {"(ninguna)": ""}.items():
        print(f"   {c:>5}  {x}")

criterios = {
    "Todas las repeticiones terminaron sin error": len(validas) == REPETICIONES,
    "BOLA 2 confirmado en ambas direcciones en todas las repeticiones": all(
        f.get("bola2_confirmados") == 2 for f in validas) and bool(validas),
    "Ninguna evidencia contiene tokens": not any(f.get("tokens_en_evidencia") for f in validas),
    "Las sesiones se liberaron en todas las repeticiones": all(f.get("sesiones_liberadas") for f in validas),
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

(carpeta_campana / "campana.json").write_text(json.dumps({
    "aplicacion": "OWASP crAPI", "modo": MODO, "repeticiones": REPETICIONES, "inicio": inicio_campana.isoformat(),
    "corridas": filas, "resumen": resumen, "estabilidad_confirmados": confirmados,
    "estabilidad_decisiones_llm": decisiones, "criterios": criterios}, ensure_ascii=False, indent=2), encoding="utf-8")
columnas = list(dict.fromkeys(k for f in filas for k in f))
with (carpeta_campana / "corridas.csv").open("w", newline="", encoding="utf-8-sig") as archivo:
    escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter=";")
    escritor.writeheader()
    escritor.writerows(filas)
print(f"\nGuardado en {carpeta_campana / 'campana.json'} y {carpeta_campana / 'corridas.csv'}")
