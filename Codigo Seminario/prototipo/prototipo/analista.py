"""Analista completo: une los pasos 1 a 5 y guarda datos/<ejecucion>/analisis.json.

Es la función que el grafo llama como segundo nodo. El modelo solo se carga si quedan candidatos
pendientes después de las reglas y el inventario, y se libera al terminar (RNF03).
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from prototipo.clasificador import MODELO, Clasificador, decidir_pendientes, verificar_modelo
from prototipo.endpoints import agrupar
from prototipo.extraccion import extraer
from prototipo.hipotesis import generar
from prototipo.modelos import ResultadoAnalisis, ResultadoExploracion
from prototipo.propiedad import Inventario, resolver

Modo = Literal["solo_reglas", "reglas_llm"]


def analizar(ruta_exploracion: str | Path, modo: Modo = "reglas_llm") -> ResultadoAnalisis:
    inicio = time.perf_counter()
    ruta_exploracion = Path(ruta_exploracion)
    r = ResultadoExploracion.model_validate_json(ruta_exploracion.read_text(encoding="utf-8"))

    candidatos = resolver(extraer(r.peticiones), Inventario(r.inventario))   # pasos 2 y 3
    pendientes = [c for c in candidatos if c.decidido_por is None]
    clasificador = None
    if modo == "reglas_llm" and pendientes:                                    # paso 4, solo si hace falta
        verificar_modelo()
        clasificador = Clasificador(r.cuentas)
    try:
        candidatos = decidir_pendientes(candidatos, {p.id: p for p in r.peticiones}, clasificador)
    finally:
        if clasificador:
            clasificador.liberar()
    hipotesis, omitidas = generar(r, candidatos)                               # paso 5

    resultado = ResultadoAnalisis(
        ejecucion=r.ejecucion, fecha=datetime.now(), modo=modo,
        modelo=MODELO if modo == "reglas_llm" else None, endpoints=agrupar(r.peticiones),
        candidatos=candidatos, hipotesis=hipotesis, omitidas=omitidas,
        consultas_llm=clasificador.consultas if clasificador else 0,
        duracion_s=round(time.perf_counter() - inicio, 1))
    destino = ruta_exploracion.parent / ("analisis.json" if modo == "reglas_llm" else "analisis_solo_reglas.json")
    destino.write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return resultado
