"""Comprobación 3: integración de LangGraph, langchain-ollama y la salida estructurada.

Verifica cuatro cosas con un grafo mínimo (Analista -> revisión humana):
  1. el modelo responde con el esquema del Analista a través de langchain-ollama;
  2. el grafo se detiene en el punto de aprobación humana;
  3. el grafo se reanuda con la decisión de la persona;
  4. el modelo se libera de la memoria al terminar.
Uso (entorno virtual activado y Ollama abierto):
    python prueba_grafo.py [modelo]        por defecto gemma4:e4b
"""
import sys
import time
from typing import Literal, TypedDict

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from ollama import generate, ps
from pydantic import BaseModel

MODELO = sys.argv[1] if len(sys.argv) > 1 else "gemma4:e4b"


class Clasificacion(BaseModel):  # mismo esquema que prueba_modelos_v2.py
    contiene_identificador: bool
    parametro: str | None
    valor: str | None
    ubicacion: Literal["ruta", "consulta", "cuerpo", "ninguna"]
    visibilidad: Literal["privado", "publico", "no_aplica"]
    cuenta_duena: Literal["A", "B", "ninguna", "desconocida"]
    justificacion: str


class Estado(TypedDict, total=False):
    peticion: str
    clasificacion: dict
    decision_humana: str


SISTEMA = """Eres el agente Analista de un sistema que busca fallas de control de acceso (IDOR/BOLA).
Indica si la petición contiene un identificador de objeto (valor que selecciona un registro concreto),
dónde está, si el objeto es privado o público y a qué cuenta pertenece.
Los parámetros de paginación, orden, filtros o moneda NO son identificadores.
Usuarios del sistema: A (id 17, a@tienda.cl) y B (id 23, b@tienda.cl)."""

CASO = ("Sesión actual: usuario A\nPetición: GET /api/pedidos/1043?moneda=CLP\n"
        'Respuesta: 200 OK {"id": 1043, "cliente_id": 17, "direccion": "Calle Canario-A-7F3", "total": 15990}')

llm = ChatOllama(model=MODELO, temperature=0, seed=42, num_ctx=4096, reasoning=False)
analista_llm = llm.with_structured_output(Clasificacion, method="json_schema")


def analista(estado: Estado) -> dict:
    c = analista_llm.invoke([("system", SISTEMA), ("human", estado["peticion"])])
    return {"clasificacion": c.model_dump()}


def revision(estado: Estado) -> dict:
    decision = interrupt({"hallazgo_por_revisar": estado["clasificacion"]})  # el grafo se detiene aquí
    return {"decision_humana": decision}


constructor = StateGraph(Estado)
constructor.add_node("analista", analista)
constructor.add_node("revision", revision)
constructor.add_edge(START, "analista")
constructor.add_edge("analista", "revision")
constructor.add_edge("revision", END)
grafo = constructor.compile(checkpointer=InMemorySaver())  # sin memoria de estado no hay pausa ni reanudación

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "prueba-1"}}
    resultados = {}

    t = time.perf_counter()
    r = grafo.invoke({"peticion": CASO}, config)
    c = r.get("clasificacion", {})
    print(f"Respuesta del Analista ({time.perf_counter() - t:.1f} s): {c}")
    resultados["1. Salida estructurada correcta"] = (
        c.get("contiene_identificador") is True and c.get("valor") == "1043" and c.get("cuenta_duena") == "A")
    resultados["2. El grafo se detuvo para la revisión humana"] = bool(r.get("__interrupt__"))

    r = grafo.invoke(Command(resume="aprobado"), config)
    resultados["3. El grafo se reanudó con la decisión"] = r.get("decision_humana") == "aprobado"

    generate(model=MODELO, prompt="", keep_alive=0)  # pide a Ollama liberar el modelo
    time.sleep(3)
    resultados["4. El modelo se liberó de la memoria"] = not any(m.model.startswith(MODELO) for m in ps().models)

    print()
    for nombre, ok in resultados.items():
        print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
