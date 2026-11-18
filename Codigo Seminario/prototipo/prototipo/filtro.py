"""Paso 4 del Explorador: filtra el tráfico capturado (RF10) y oculta secretos (RNF06).

Solo pasa al Analista lo que puede contener un identificador de objeto: peticiones a la API de la
aplicación autorizada, con respuesta JSON. Cada descarte se cuenta por motivo, para informar la
cobertura alcanzada (Tabla 6.2).
"""
import json
from collections import Counter
from urllib.parse import urlsplit

from prototipo.modelos import Alcance, PeticionCapturada

# Claves cuyo valor nunca se guarda en la evidencia (credenciales y tokens)
CLAVES_SECRETAS = {"password", "passwordrepeat", "clave", "token", "totpsecret", "authorization"}
OCULTO = "***"


def _ocultar(dato):
    if isinstance(dato, dict):
        return {k: OCULTO if k.lower() in CLAVES_SECRETAS else _ocultar(v) for k, v in dato.items()}
    if isinstance(dato, list):
        return [_ocultar(v) for v in dato]
    return dato


def ocultar_secretos(texto: str) -> str:
    """Reemplaza el valor de las claves secretas en un JSON. Si el texto no es JSON, lo deja igual."""
    if not texto:
        return texto
    try:
        return json.dumps(_ocultar(json.loads(texto)), ensure_ascii=False)
    except ValueError:
        return texto


def motivo_descarte(p: PeticionCapturada, alcance: Alcance) -> str | None:
    """Devuelve por qué se descarta una petición, o None si pasa el filtro. El orden importa."""
    host_alcance = urlsplit(alcance.url_base).netloc
    if p.host and p.host != host_alcance:
        return "fuera_del_alcance"          # otro servidor (p. ej. servicios del navegador)
    if p.estado == 101:
        return "websocket"                  # fuera del alcance del trabajo (sección 3.3)
    if not p.ruta.startswith(tuple(alcance.prefijos_api)):
        return "recurso_estatico"           # páginas, scripts, imágenes, fuentes
    if p.estado == 304 or not p.cuerpo_respuesta:
        return "sin_contenido"              # respuesta en caché o vacía: no hay nada que analizar
    if "json" not in p.tipo_contenido:
        return "no_json"
    return None


def filtrar(peticiones: list[PeticionCapturada], alcance: Alcance) -> tuple[list[PeticionCapturada], dict[str, int]]:
    """Aplica el filtro, elimina duplicados exactos y oculta secretos en lo que se conserva."""
    conservadas, descartadas, vistas = [], Counter(), set()
    for p in peticiones:
        motivo = motivo_descarte(p, alcance)
        if motivo is None:
            clave = (p.sesion, p.metodo, p.ruta, p.consulta, p.cuerpo_peticion)
            if clave in vistas:
                motivo = "duplicada"        # misma petición, misma sesión: el Analista la vería dos veces
            else:
                vistas.add(clave)
        if motivo:
            descartadas[motivo] += 1
            continue
        conservadas.append(p.model_copy(update={
            "cuerpo_peticion": ocultar_secretos(p.cuerpo_peticion),
            "cuerpo_respuesta": ocultar_secretos(p.cuerpo_respuesta)}))
    return conservadas, dict(descartadas)
