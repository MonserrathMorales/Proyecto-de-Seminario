"""Paso 1 del Analista: agrupa las peticiones capturadas por endpoint (RF04).

Dos peticiones pertenecen al mismo endpoint si tienen el mismo método, la misma ruta una vez
reemplazados los identificadores por {id}, y los mismos nombres de parámetros de consulta.
Así, GET /rest/basket/6 (de A) y GET /rest/basket/7 (de B) son un solo endpoint, GET /rest/basket/{id}.
"""
import re
from urllib.parse import parse_qsl

from prototipo.modelos import Endpoint, PeticionCapturada

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HEX_LARGO = re.compile(r"^[0-9a-f]{16,}$", re.I)            # p. ej. ObjectId de MongoDB (24 caracteres)
_TOKEN = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{12,}$")           # alfanumérico largo con al menos un dígito


def es_valor_identificador(segmento: str) -> bool:
    """¿Parece un identificador? Números, UUID, hexadecimales largos o tokens alfanuméricos largos."""
    return segmento.isdigit() or bool(_UUID.match(segmento) or _HEX_LARGO.match(segmento) or _TOKEN.match(segmento))


def plantilla(ruta: str) -> str:
    """/rest/basket/6 -> /rest/basket/{id}. Quita la barra final para que /api/x y /api/x/ coincidan."""
    partes = ["{id}" if s and es_valor_identificador(s) else s for s in ruta.split("/")]
    resultado = "/".join(partes)
    return resultado.rstrip("/") or "/"


def parametros_consulta(consulta: str) -> list[str]:
    return sorted({k for k, _ in parse_qsl(consulta, keep_blank_values=True)})


def clave_endpoint(p: PeticionCapturada) -> str:
    params = parametros_consulta(p.consulta)
    return f"{p.metodo} {plantilla(p.ruta)}" + (f"?{'&'.join(params)}" if params else "")


def agrupar(peticiones: list[PeticionCapturada]) -> list[Endpoint]:
    """Devuelve los endpoints en orden de aparición, cada uno con sus peticiones y sesiones."""
    grupos: dict[str, Endpoint] = {}
    for p in peticiones:
        clave = clave_endpoint(p)
        if clave not in grupos:
            grupos[clave] = Endpoint(clave=clave, metodo=p.metodo, plantilla=plantilla(p.ruta),
                                     parametros_consulta=parametros_consulta(p.consulta),
                                     peticiones=[], sesiones=[], autenticada=False)
        e = grupos[clave]
        e.peticiones.append(p.id)
        if p.sesion not in e.sesiones:
            e.sesiones.append(p.sesion)
        e.autenticada = e.autenticada or p.autenticada
    return list(grupos.values())
