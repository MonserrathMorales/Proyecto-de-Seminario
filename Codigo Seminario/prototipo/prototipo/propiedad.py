"""Paso 3 del Analista: decide con el inventario los candidatos que corresponden a objetos sembrados.

Si un candidato es un objeto que el propio sistema creó, su dueño se conoce por construcción y no
hace falta preguntarle al modelo. Responde al segundo error del 13 de noviembre: sin un dato de
propiedad en la respuesta, los modelos asumían como dueña a la cuenta de la sesión.

La búsqueda usa el endpoint y no solo el número, porque el mismo id puede ser objetos distintos
(en Juice Shop, el 7 es la dirección de A y también la canasta de B).
"""
import re

from prototipo import juice_shop as adaptador
from prototipo.modelos import Candidato, ObjetoSembrado


def _plantilla(clave_endpoint: str) -> str:
    """'GET /rest/basket/{id}?x' -> '/rest/basket/{id}'"""
    return clave_endpoint.split(" ", 1)[1].split("?")[0]


class Inventario:
    """Índices del inventario: por (endpoint, id) para la ruta, y por (tipo, id) para consulta y cuerpo."""

    def __init__(self, objetos: list[ObjetoSembrado]):
        self.por_endpoint: dict[tuple[str, str], ObjetoSembrado] = {}
        self.por_tipo: dict[tuple[str, str], ObjetoSembrado] = {}
        self.uso_respaldo = False  # True si algún objeto no traía su endpoint (evidencia anterior al cambio)
        for o in objetos:
            endpoint = o.endpoint
            if endpoint is None:
                endpoint = adaptador.ENDPOINTS.get(o.tipo)
                self.uso_respaldo = True
            if endpoint:
                self.por_endpoint[(endpoint, o.id)] = o
            self.por_tipo[(o.tipo, o.id)] = o

    def buscar(self, c: Candidato) -> ObjetoSembrado | None:
        if c.ubicacion == "ruta":
            return self.por_endpoint.get((_plantilla(c.endpoint), c.valor))
        nombre = re.split(r"[.\[]", c.parametro)[-1].lower()   # "orden.BasketId" -> "basketid"
        tipo = adaptador.PARAMETROS.get(nombre)
        return self.por_tipo.get((tipo, c.valor)) if tipo else None


def resolver(candidatos: list[Candidato], inventario: Inventario) -> list[Candidato]:
    """Completa los candidatos que están en el inventario; los demás quedan pendientes para el paso 4."""
    resultado = []
    for c in candidatos:
        o = inventario.buscar(c)
        if o is None:
            resultado.append(c)
            continue
        nota = f"{o.tipo} sembrado en la cuenta {o.cuenta}"
        if o.cuenta != c.sesion:  # en una navegación normal no debería ocurrir: sería ya un acceso a un objeto ajeno
            nota += f"; ATENCIÓN: lo pidió la sesión {c.sesion} durante la exploración"
        resultado.append(c.model_copy(update={
            "decidido_por": "inventario", "es_identificador": True, "visibilidad": "privado",
            "cuenta_duena": o.cuenta, "objeto": o.tipo, "justificacion": nota}))
    return resultado
