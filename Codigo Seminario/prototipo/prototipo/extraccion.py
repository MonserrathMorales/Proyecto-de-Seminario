"""Paso 2 del Analista: extrae con reglas los parámetros que podrían identificar un objeto.

Solo mira la PETICIÓN (ruta, consulta y cuerpo), nunca la respuesta. En la prueba del 13 de
noviembre, los modelos tomaban ids de la respuesta como si fueran de la petición; con reglas
ese error no puede ocurrir. Lo que las reglas no pueden decidir (si un candidato es de verdad
un identificador de objeto, y si el objeto es privado) se resuelve en los pasos 3 y 4.
"""
import json
import re
from urllib.parse import parse_qsl

from prototipo.endpoints import clave_endpoint, es_valor_identificador
from prototipo.modelos import Candidato, PeticionCapturada

# Nombres con forma de identificador: id, uid, uuid, *_id, *_uuid (en cualquier combinación de mayúsculas),
# y *Id o *ID después de una minúscula o un dígito (BasketId, userID). La terminación "id" en minúsculas no
# basta: "paid", "valid" o "android" no son identificadores.
_NOMBRE_ID = re.compile(r"^(?i:id|uid|uuid)$|(?i:_id|_uuid)$|[a-z0-9]I[dD]$")
# Parámetros de paginación, orden o filtro: nunca son identificadores de objeto (caso C3 de la Prueba 1)
NO_IDENTIFICADORES = {"page", "pagina", "limit", "offset", "size", "tamano", "per_page", "sort", "order",
                      "orden", "moneda", "currency", "lang", "idioma", "q", "query", "search", "fields",
                      "quantity", "cantidad", "rating"}


def _parece_identificador(nombre: str, valor) -> bool:
    if nombre.lower() in NO_IDENTIFICADORES or valor is None or isinstance(valor, (bool, dict, list)):
        return False
    texto = str(valor).strip()
    if not texto:
        return False
    return bool(_NOMBRE_ID.search(nombre)) or es_valor_identificador(texto)


def _aplanar(dato, prefijo=""):
    """{"a": {"b_id": 3}} -> [("a.b_id", 3)]. Las listas se recorren con su índice."""
    if isinstance(dato, dict):
        for k, v in dato.items():
            yield from _aplanar(v, f"{prefijo}.{k}" if prefijo else str(k))
    elif isinstance(dato, list):
        for i, v in enumerate(dato):
            yield from _aplanar(v, f"{prefijo}[{i}]")
    else:
        yield prefijo, dato


def candidatos_de(p: PeticionCapturada) -> list[Candidato]:
    clave = clave_endpoint(p)
    base = {"peticion": p.id, "endpoint": clave, "sesion": p.sesion}
    encontrados = []

    # 1. Ruta: segmentos con forma de identificador; el nombre es el segmento anterior (el recurso)
    segmentos = p.ruta.split("/")
    for i, s in enumerate(segmentos):
        if s and es_valor_identificador(s):
            recurso = next((x for x in reversed(segmentos[:i]) if x and not es_valor_identificador(x)), "ruta")
            encontrados.append(Candidato(**base, parametro=recurso, valor=s, ubicacion="ruta"))

    # 2. Consulta: parámetros con nombre o valor de identificador
    for nombre, valor in parse_qsl(p.consulta, keep_blank_values=True):
        if _parece_identificador(nombre, valor):
            encontrados.append(Candidato(**base, parametro=nombre, valor=valor, ubicacion="consulta"))

    # 3. Cuerpo JSON: claves con nombre de identificador o valores con forma de identificador
    try:
        cuerpo = json.loads(p.cuerpo_peticion) if p.cuerpo_peticion else None
    except ValueError:
        cuerpo = None
    if cuerpo is not None:
        for ruta_clave, valor in _aplanar(cuerpo):
            nombre = re.split(r"[.\[]", ruta_clave)[-1] or ruta_clave
            if valor != "***" and _parece_identificador(nombre, valor):
                encontrados.append(Candidato(**base, parametro=ruta_clave, valor=str(valor), ubicacion="cuerpo"))
    return encontrados


def extraer(peticiones: list[PeticionCapturada]) -> list[Candidato]:
    """Candidatos de las sesiones A y B, sin repetir el mismo (endpoint, sesión, parámetro, valor, ubicación).

    La sesión anónima no tiene objetos propios: sus peticiones no generan candidatos.
    """
    vistos, resultado = set(), []
    for p in peticiones:
        if p.sesion not in ("A", "B"):
            continue
        for c in candidatos_de(p):
            clave = (c.endpoint, c.sesion, c.parametro, c.valor, c.ubicacion)
            if clave not in vistos:
                vistos.add(clave)
                resultado.append(c)
    return resultado
