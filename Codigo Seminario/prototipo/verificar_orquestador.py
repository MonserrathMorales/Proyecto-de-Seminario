"""Orquestador: ejecuta el grafo REAL de LangGraph con los tres agentes, sin Juice Shop ni navegador.

Qué es real y qué es simulado en esta prueba:
  - reales: el grafo (nodos, aristas, estado, puntos de control, cierre), el Analista y el agente de
    Validación y Remediación;
  - simulados: el Explorador, que entrega la evidencia más reciente ya guardada en datos/, y la
    aplicación, que contesta con esas mismas respuestas (simulacion.py).
Comprueba que el orquestador encadena los tres agentes, pasa el estado de uno a otro, guarda el
registro y cierra ordenadamente cuando falla cualquiera de las etapas.
Todo se escribe en una carpeta temporal: datos/ no se modifica.

No reemplaza a la corrida real (verificar_validacion.py --completo), que es la única que prueba el
navegador, el proxy y Juice Shop.
Uso (desde la carpeta prototipo, con el entorno virtual activado; solo necesita LangGraph):
    python verificar_orquestador.py
"""
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


def _simular_si_falta(nombre: str, **atributos) -> None:
    """Si un paquete del Explorador real no está instalado, lo reemplaza por un módulo vacío.

    El Explorador real no se usa en esta prueba, pero grafo.py lo importa.
    """
    try:
        instalado = importlib.util.find_spec(nombre) is not None
    except (ImportError, ValueError):
        instalado = False
    if not instalado:
        modulo = types.ModuleType(nombre)
        modulo.__dict__.update(atributos)
        sys.modules[nombre] = modulo


_simular_si_falta("mitmproxy", http=types.ModuleType("mitmproxy.http"), io=types.ModuleType("mitmproxy.io"))
_simular_si_falta("playwright")
_simular_si_falta("playwright.sync_api", TimeoutError=TimeoutError, sync_playwright=None)

from prototipo import grafo  # noqa: E402
from prototipo.grafo import SESIONES, construir  # noqa: E402
from prototipo.juice_shop import SesionPreparada  # noqa: E402
from prototipo.modelos import Alcance, ResultadoExploracion, ResultadoValidacion  # noqa: E402
from simulacion import AplicacionSimulada  # noqa: E402

ETAPAS = ["explorador", "analista", "validacion", "cerrar"]
archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
evidencia = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
tokens = {c.nombre: f"TOKEN-SIMULADO-{c.nombre}" for c in evidencia.cuentas}
app = AplicacionSimulada(evidencia, alcance.url_base, tokens)
print(f"Evidencia que entrega el Explorador simulado: {archivo}\n")


def explorar_simulado(_alcance):
    grafo.mod_explorador.guardar(evidencia)  # la escribe en la carpeta temporal
    return evidencia, {c.nombre: SesionPreparada(cuenta=c, token=tokens[c.nombre]) for c in evidencia.cuentas}


def fallar(mensaje):
    def funcion(*_args, **_kwargs):
        raise RuntimeError(mensaje)
    return funcion


explorar_real, analizar_real = grafo.mod_explorador.explorar, grafo.mod_analista.analizar
validar_real = grafo.mod_validacion.validar


def validar_simulado(ruta_analisis, alcance_recibido, sesiones):
    return validar_real(ruta_analisis, alcance_recibido, sesiones, http=app, pausa=0)


def correr(hilo: str):
    """Ejecuta el grafo y devuelve el estado final, el registro guardado y lo que quedó en el punto de control."""
    config = {"configurable": {"thread_id": hilo}}
    estado = g.invoke({"ruta_alcance": "alcance_juice.json", "modo_analista": "solo_reglas"}, config)
    # Con ejecución, el registro va a su carpeta; si el Explorador falló, a una carpeta "<fecha>_fallida"
    carpeta = Path(tmp) / estado["ejecucion"] if estado.get("ejecucion") else next(Path(tmp).glob("*_fallida"))
    registro = json.loads((carpeta / "registro.json").read_text(encoding="utf-8"))
    return estado, registro, carpeta, json.dumps(g.get_state(config).values, default=str)


def etapas(estado):
    return [e["etapa"] for e in estado["registro"]]


with tempfile.TemporaryDirectory() as tmp:
    grafo.mod_explorador.CARPETA_DATOS = Path(tmp)
    g = construir()
    nodos = [n for n in g.get_graph().nodes if not n.startswith("__")]
    print("Nodos del grafo:", nodos)

    # ---------- 1. Corrida normal ----------
    grafo.mod_explorador.explorar, grafo.mod_validacion.validar = explorar_simulado, validar_simulado
    estado, registro, carpeta, punto_control = correr("normal")
    print("\n1. Corrida normal")
    for e in estado["registro"]:
        extra = {k: x for k, x in e.items() if k not in ("etapa", "inicio", "duracion_s", "resultado")}
        print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>5} s  {extra}")
    archivos = sorted(f.name for f in carpeta.iterdir())
    texto_validacion = Path(estado["ruta_validacion"]).read_text(encoding="utf-8")
    v = ResultadoValidacion.model_validate_json(texto_validacion)
    texto_registro = (carpeta / "registro.json").read_text(encoding="utf-8")
    llamadas_normales = len(app.llamadas)
    normal = {
        "El grafo tiene los cuatro nodos": nodos == ETAPAS,
        "Las cuatro etapas corrieron en orden y terminaron bien": etapas(estado) == ETAPAS
            and all(e["resultado"] == "ok" for e in estado["registro"]) and not estado.get("error"),
        "Cada agente recibió la evidencia del anterior y dejó la suya": archivos == [
            "analisis_solo_reglas.json", "exploracion.json", "registro.json", "validacion_solo_reglas.json"],
        "El resumen del estado coincide con la evidencia guardada":
            estado["resumen_validacion"]["confirmado"] == v.resumen["confirmado"] >= 1
            and estado["resumen_validacion"]["enviadas"] == v.enviadas == llamadas_normales
            and estado["resumen_analisis"]["hipotesis"] == len(v.pares),
        "El registro guardado tiene las cuatro etapas y ningún error":
            [e["etapa"] for e in registro["etapas"]] == ETAPAS and registro["error"] is None,
        "Ni el estado del grafo, ni el registro, ni la validación contienen tokens": all(
            "TOKEN-SIMULADO" not in t and "Bearer" not in t for t in (punto_control, texto_registro, texto_validacion)),
        "Las sesiones se liberaron de la memoria al cerrar": estado["ejecucion"] not in SESIONES,
    }

    # ---------- 2. Falla el Explorador ----------
    grafo.mod_explorador.explorar = fallar("aplicación inalcanzable (simulado)")
    e2, r2, _, _ = correr("falla-explorador")
    print(f"\n2. Falla el Explorador   -> etapas {etapas(e2)}   error: {e2.get('error')}")

    # ---------- 3. Falla el Analista ----------
    grafo.mod_explorador.explorar = explorar_simulado
    grafo.mod_analista.analizar = fallar("Ollama no responde (simulado)")
    e3, r3, _, _ = correr("falla-analista")
    print(f"3. Falla el Analista     -> etapas {etapas(e3)}   error: {e3.get('error')}")
    llamadas_tras_analista = len(app.llamadas)

    # ---------- 4. Falla la Validación ----------
    grafo.mod_analista.analizar = analizar_real
    grafo.mod_validacion.validar = fallar("autorización vencida (simulado)")
    e4, r4, _, _ = correr("falla-validacion")
    print(f"4. Falla la Validación   -> etapas {etapas(e4)}   error: {e4.get('error')}")

    grafo.mod_explorador.explorar, grafo.mod_validacion.validar = explorar_real, validar_real

errores = {
    "Si falla el Explorador, el flujo salta a cerrar y no analiza ni valida":
        etapas(e2) == ["explorador", "cerrar"] and e2.get("error", "").startswith("Explorador:")
        and r2["error"] == e2["error"],
    "Si falla el Analista, el flujo salta a cerrar y no se envía ninguna petición":
        etapas(e3) == ["explorador", "analista", "cerrar"] and e3.get("error", "").startswith("Analista:")
        and llamadas_tras_analista == llamadas_normales and r3["error"] == e3["error"],
    "Si falla la Validación, el error queda registrado y el flujo cierra":
        etapas(e4) == ETAPAS and e4.get("error", "").startswith("Validación:") and r4["error"] == e4["error"],
    "En las tres fallas las sesiones también se liberan de la memoria": not SESIONES,
}
print()
for nombre, ok in {**normal, **errores}.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
