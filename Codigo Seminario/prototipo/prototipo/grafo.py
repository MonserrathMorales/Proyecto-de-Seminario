"""Orquestador: el flujo del sistema como un grafo de estados de LangGraph (Tabla 6.1).

El orden de las etapas está fijado en el código (flujo de trabajo, no agente autónomo; sección 6.2).
Flujo actual: explorador -> analista -> validacion -> cerrar. Si una etapa falla, salta a "cerrar".

El estado solo guarda datos serializables y sin secretos. Las sesiones con sus tokens quedan en
SESIONES, un registro en memoria que nunca se escribe en disco ni en los puntos de control del grafo.
"""
import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from prototipo import analista as mod_analista
from prototipo import explorador as mod_explorador
from prototipo import validacion as mod_validacion
from prototipo.modelos import Alcance
from prototipo.sesion import SesionPreparada

SESIONES: dict[str, dict[str, SesionPreparada]] = {}  # ejecucion -> sesiones (solo en memoria)


class Estado(TypedDict, total=False):
    ruta_alcance: str                                   # entrada: archivo de alcance (RF01)
    ejecucion: str                                      # identificador de la ejecución
    ruta_exploracion: str                               # evidencia del Explorador
    resumen_exploracion: dict                           # conteos para el registro y el reporte
    modo_analista: str                                  # entrada opcional: "reglas_llm" (defecto) o "solo_reglas"
    ruta_analisis: str                                  # hipótesis del Analista
    resumen_analisis: dict
    ruta_validacion: str                                # pares cruzados, veredictos y correcciones sugeridas
    resumen_validacion: dict
    error: str                                         # si una etapa falla, el flujo va a "cerrar"
    registro: Annotated[list[dict], operator.add]       # una entrada por etapa (salida del Orquestador)


def _entrada(etapa: str, inicio: datetime, resultado: str, **detalle) -> dict:
    fin = datetime.now()
    return {"etapa": etapa, "inicio": inicio.isoformat(timespec="seconds"),
            "duracion_s": round((fin - inicio).total_seconds(), 1), "resultado": resultado, **detalle}


# ---------- Nodos ----------
def nodo_explorador(estado: Estado) -> dict:
    inicio = datetime.now()
    try:
        alcance = Alcance.model_validate_json(Path(estado["ruta_alcance"]).read_text(encoding="utf-8"))
        r, sesiones = mod_explorador.explorar(alcance)
    except Exception as e:  # el error queda registrado y el flujo se cierra ordenadamente
        return {"error": f"Explorador: {e}", "registro": [_entrada("explorador", inicio, "error", detalle=str(e))]}
    SESIONES[r.ejecucion] = sesiones
    resumen = {"conservadas": len(r.peticiones), "descartadas": r.descartadas,
               "por_sesion": {s: sum(p.sesion == s for p in r.peticiones) for s in ("A", "B", "anonima")},
               "inventario": len(r.inventario)}
    return {"ejecucion": r.ejecucion,
            "ruta_exploracion": str(mod_explorador.CARPETA_DATOS / r.ejecucion / "exploracion.json"),
            "resumen_exploracion": resumen,
            "registro": [_entrada("explorador", inicio, "ok", **resumen)]}


def nodo_analista(estado: Estado) -> dict:
    inicio = datetime.now()
    modo = estado.get("modo_analista", "reglas_llm")
    try:
        a = mod_analista.analizar(estado["ruta_exploracion"], modo)
    except Exception as e:
        return {"error": f"Analista: {e}", "registro": [_entrada("analista", inicio, "error", detalle=str(e))]}
    resumen = {"modo": a.modo, "endpoints": len(a.endpoints), "candidatos": len(a.candidatos),
               "por_inventario": sum(c.decidido_por == "inventario" for c in a.candidatos),
               "consultas_llm": a.consultas_llm, "hipotesis": len(a.hipotesis), "omitidas": a.omitidas}
    nombre = "analisis.json" if modo == "reglas_llm" else "analisis_solo_reglas.json"
    return {"ruta_analisis": str(Path(estado["ruta_exploracion"]).parent / nombre),
            "resumen_analisis": resumen, "registro": [_entrada("analista", inicio, "ok", **resumen)]}


def nodo_validacion(estado: Estado) -> dict:
    inicio = datetime.now()
    try:
        alcance = Alcance.model_validate_json(Path(estado["ruta_alcance"]).read_text(encoding="utf-8"))
        sesiones = SESIONES.get(estado["ejecucion"])
        if sesiones is None:
            raise RuntimeError("no hay sesiones en memoria para esta ejecución")
        v = mod_validacion.validar(estado["ruta_analisis"], alcance, sesiones)
    except Exception as e:
        return {"error": f"Validación: {e}", "registro": [_entrada("validacion", inicio, "error", detalle=str(e))]}
    resumen = {"hipotesis": len(v.pares), "enviadas": v.enviadas, "omitidas": v.omitidas, **v.resumen}
    return {"ruta_validacion": str(mod_validacion.ruta_salida(estado["ruta_analisis"])),
            "resumen_validacion": resumen, "registro": [_entrada("validacion", inicio, "ok", **resumen)]}


def nodo_cerrar(estado: Estado) -> dict:
    """Guarda el registro de la ejecución junto a su evidencia y libera las sesiones de la memoria."""
    inicio = datetime.now()
    ejecucion = estado.get("ejecucion") or inicio.strftime("%Y%m%d_%H%M%S_fallida")
    carpeta = mod_explorador.CARPETA_DATOS / ejecucion
    carpeta.mkdir(parents=True, exist_ok=True)
    entrada = _entrada("cerrar", inicio, "error" if estado.get("error") else "ok")
    (carpeta / "registro.json").write_text(json.dumps(
        {"ejecucion": ejecucion, "error": estado.get("error"), "etapas": estado.get("registro", []) + [entrada]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    SESIONES.pop(ejecucion, None)
    return {"registro": [entrada]}


def _despues_de(etapa_siguiente: str):
    """Si la etapa anterior falló, salta directo a cerrar."""
    return lambda estado: "cerrar" if estado.get("error") else etapa_siguiente


# ---------- Grafo ----------
def construir():
    g = StateGraph(Estado)
    g.add_node("explorador", nodo_explorador)
    g.add_node("analista", nodo_analista)
    g.add_node("validacion", nodo_validacion)
    g.add_node("cerrar", nodo_cerrar)
    g.add_edge(START, "explorador")
    g.add_conditional_edges("explorador", _despues_de("analista"), ["analista", "cerrar"])
    g.add_conditional_edges("analista", _despues_de("validacion"), ["validacion", "cerrar"])
    # Los puntos de aprobación humana (RF07) se agregarán aquí, entre "validacion" y "cerrar"
    g.add_edge("validacion", "cerrar")
    g.add_edge("cerrar", END)
    return g.compile(checkpointer=InMemorySaver())
