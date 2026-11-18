"""Agente de Validación y Remediación completo: une los pasos 1 a 4 y guarda datos/<ejecucion>/validacion.json.

Es la función que el grafo llama como tercer nodo:
  1. guardia de alcance (cruce.py);
  2. línea base y cruce de cada hipótesis (cruce.py);
  3. veredicto del oráculo determinista (oraculo.py);
  4. corrección sugerida para los hallazgos confirmados (remediacion.py).
Es determinista: no usa el modelo ni el navegador, por lo que corre después de que el Analista liberó
la memoria (RNF03). Las sesiones llegan en memoria y sus tokens no se escriben en la evidencia (RNF06).
"""
import time
from datetime import datetime
from pathlib import Path

import requests

from prototipo.cruce import PAUSA, cruzar
from prototipo.modelos import (Alcance, Hipotesis, ParCruzado, ResultadoAnalisis, ResultadoExploracion,
                               ResultadoValidacion, Veredicto)
from prototipo.oraculo import juzgar
from prototipo.remediacion import sugerir
from prototipo.sesion import SesionPreparada

CLASES = ("confirmado", "dudoso", "descartado")


def ruta_salida(ruta_analisis: str | Path) -> Path:
    """analisis.json -> validacion.json; analisis_solo_reglas.json -> validacion_solo_reglas.json."""
    ruta_analisis = Path(ruta_analisis)
    return ruta_analisis.with_name("validacion" + ruta_analisis.stem.removeprefix("analisis") + ".json")


def emitir_veredictos(pares: list[ParCruzado], hipotesis: list[Hipotesis]) -> list[Veredicto]:
    """Pasos 3 y 4. Función pura: sirve también para volver a juzgar pares ya guardados."""
    por_id = {h.id: h for h in hipotesis}
    veredictos = []
    for par in pares:
        v = juzgar(par, por_id[par.hipotesis])
        veredictos.append(v.model_copy(update={"remediacion": sugerir(v)}))
    return veredictos


def validar(ruta_analisis: str | Path, alcance: Alcance, sesiones: dict[str, SesionPreparada],
            http=requests, pausa: float = PAUSA) -> ResultadoValidacion:
    """http y pausa solo se cambian en las pruebas, para validar sin la aplicación real."""
    inicio = time.perf_counter()
    alcance.comprobar_vigencia()  # sin autorización vigente no se envía nada (RF01)
    ruta_analisis = Path(ruta_analisis)
    a = ResultadoAnalisis.model_validate_json(ruta_analisis.read_text(encoding="utf-8"))
    r = ResultadoExploracion.model_validate_json(
        (ruta_analisis.parent / "exploracion.json").read_text(encoding="utf-8"))

    pares, enviadas, omitidas = cruzar(a.hipotesis, {p.id: p for p in r.peticiones}, alcance, sesiones,
                                       http, pausa)                              # pasos 1 y 2
    veredictos = emitir_veredictos(pares, a.hipotesis)                           # pasos 3 y 4

    resultado = ResultadoValidacion(
        ejecucion=a.ejecucion, fecha=datetime.now(), pares=pares, veredictos=veredictos,
        resumen={clase: sum(v.clase == clase for v in veredictos) for clase in CLASES},
        enviadas=enviadas, omitidas=omitidas, duracion_s=round(time.perf_counter() - inicio, 1))
    ruta_salida(ruta_analisis).write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return resultado
