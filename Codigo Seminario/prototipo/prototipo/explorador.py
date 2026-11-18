"""Explorador completo: prepara las cuentas, captura el tráfico, lo filtra y guarda el resultado.

Es la función que el grafo de LangGraph llamará como primer nodo (paso 5).
"""
from datetime import datetime
from pathlib import Path

from prototipo.captura import capturar
from prototipo.filtro import filtrar
from prototipo.juice_shop import SesionPreparada, preparar
from prototipo.modelos import Alcance, ResultadoExploracion

CARPETA_DATOS = Path("datos")


def explorar(alcance: Alcance) -> tuple[ResultadoExploracion, dict[str, SesionPreparada]]:
    """Devuelve el resultado (que se guarda en disco) y las sesiones (que solo viven en memoria)."""
    inicio = datetime.now()
    alcance.comprobar_vigencia()  # sin autorización vigente no se toca la aplicación (RF01)
    sesiones = preparar(alcance)
    capturadas = capturar(alcance, sesiones)
    conservadas, descartadas = filtrar(capturadas, alcance)

    resultado = ResultadoExploracion(
        ejecucion=inicio.strftime("%Y%m%d_%H%M%S"), fecha=inicio, aplicacion=alcance.aplicacion,
        cuentas=[s.cuenta for s in sesiones.values()],
        inventario=[o for s in sesiones.values() for o in s.inventario],
        peticiones=conservadas, descartadas=descartadas)
    guardar(resultado)
    return resultado, sesiones


def guardar(resultado: ResultadoExploracion) -> Path:
    """Guarda la evidencia de la ejecución en datos/<ejecucion>/exploracion.json (RNF04)."""
    carpeta = CARPETA_DATOS / resultado.ejecucion
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "exploracion.json"
    ruta.write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return ruta
