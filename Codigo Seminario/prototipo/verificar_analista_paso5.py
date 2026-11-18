"""Paso 5 del Analista: genera las hipótesis y prueba el Analista como nodo del grafo.

Parte 1 (siempre): analiza la evidencia más reciente en los dos modos. No necesita Juice Shop;
                   Ollama solo se usa si quedan candidatos pendientes (con tu evidencia, ninguno).
Parte 2 (opcional): con --completo, ejecuta el grafo entero explorador -> analista -> cerrar.
                   Necesita Juice Shop recién reiniciado y Ollama abierto.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_analista_paso5.py
    python verificar_analista_paso5.py --completo
"""
import json
import sys
from pathlib import Path

from prototipo.analista import analizar
from prototipo.hipotesis import generar
from prototipo.modelos import Candidato, ResultadoAnalisis, ResultadoExploracion

archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
r = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
print(f"Parte 1. Evidencia: {archivo}\n")
solo = analizar(archivo, "solo_reglas")
llm = analizar(archivo, "reglas_llm")

print(f" {'Id':<6}{'Tipo':<11}{'Endpoint':<30}{'Valor':<6}{'Dueño':<6}{'Prueba con':<11}{'Verificación'}")
for h in llm.hipotesis:
    detalle = h.canario or (f"buscar {h.marca_dueno}" if h.marca_dueno else "")
    print(f" {h.id:<6}{h.tipo:<11}{h.endpoint[:29]:<30}{h.valor or '-':<6}{h.cuenta_duena:<6}"
          f"{h.sesion_prueba:<11}{h.verificacion} {detalle}")
print(f"\n Hipótesis: {len(llm.hipotesis)}   Pruebas omitidas: {llm.omitidas or 'ninguna'}")
print(f" Consultas al modelo: {llm.consultas_llm}   Duración del análisis: {llm.duracion_s} s")

# Hipótesis desde un candidato decidido por el LLM (caso J50 del paso 4), sin Ollama
p_llm = next(p for p in r.peticiones if p.sesion == "A" and p.metodo == "GET")
c_llm = Candidato(peticion=p_llm.id, endpoint="GET /api/Items/{id}", sesion="A", parametro="Items", valor="12",
                  ubicacion="ruta", decidido_por="llm", es_identificador=True, visibilidad="privado",
                  cuenta_duena="desconocida")
h_llm = [h for h in generar(r, [c_llm])[0] if h.endpoint == c_llm.endpoint]

guardado = ResultadoAnalisis.model_validate_json((archivo.parent / "analisis.json").read_text(encoding="utf-8"))
texto = (archivo.parent / "analisis.json").read_text(encoding="utf-8")
horizontales = {(h.endpoint, h.valor, h.sesion_prueba) for h in llm.hipotesis if h.tipo == "horizontal"}
dirs = [h for h in llm.hipotesis if "Addresss/{id}" in h.endpoint]
cans = [h for h in llm.hipotesis if "basket/{id}" in h.endpoint]
criterios = {
    "Prueba horizontal para cada canasta y dirección, con la otra cuenta": {
        ("GET /rest/basket/{id}", "6", "B"), ("GET /rest/basket/{id}", "7", "A"),
        ("GET /api/Addresss/{id}", "7", "B"), ("GET /api/Addresss/{id}", "8", "A")} <= horizontales,
    "Cada objeto privado también se prueba sin sesión": all(
        any(h.tipo == "sin_sesion" and (h.endpoint, h.valor) == (x.endpoint, x.valor) for h in llm.hipotesis)
        for x in llm.hipotesis if x.tipo == "horizontal"),
    "Direcciones se verifican con su canario; canastas con el inventario":
        all(h.verificacion == "canario" and h.canario and f"-{h.cuenta_duena}-" in h.canario for h in dirs)
        and all(h.verificacion == "inventario" and h.marca_dueno for h in cans),
    "Solo pruebas de lectura (GET)": all(
        next(p for p in r.peticiones if p.id == h.peticion_origen).metodo == "GET" for h in llm.hipotesis),
    "Un privado decidido por el LLM queda sin verificación determinista":
        bool(h_llm) and all(h.verificacion == "sin_verificacion" for h in h_llm),
    "Con esta evidencia ambos modos coinciden y el modelo no se usó":
        [h.model_dump() for h in solo.hipotesis] == [h.model_dump() for h in llm.hipotesis] and llm.consultas_llm == 0,
    "El análisis se guarda, se lee sin pérdida y sin tokens": guardado.hipotesis == llm.hipotesis
        and "Bearer" not in texto and "eyJ" not in texto,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Parte 2: grafo completo ----------
if "--completo" in sys.argv:
    from prototipo.grafo import construir
    print("\nParte 2. Grafo completo: explorador -> analista -> validacion -> cerrar (se abre el navegador)...")
    estado = construir().invoke({"ruta_alcance": "alcance_juice.json"}, {"configurable": {"thread_id": "analista"}})
    for e in estado["registro"]:
        extra = {k: v for k, v in e.items() if k not in ("etapa", "inicio", "duracion_s", "resultado")}
        print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>6} s  {extra}")
    etapas = [e["etapa"] for e in estado["registro"]]
    ok = etapas == ["explorador", "analista", "validacion", "cerrar"] and not estado.get("error") \
        and Path(estado.get("ruta_analisis", "")).exists()
    print(f"\n[{'OK' if ok else 'FALLA'}] El grafo ejecutó explorador, analista y cerrar, y guardó las hipótesis")
    if ok:
        a = json.loads(Path(estado["ruta_analisis"]).read_text(encoding="utf-8"))
        print(f"   {len(a['hipotesis'])} hipótesis en {estado['ruta_analisis']}")
