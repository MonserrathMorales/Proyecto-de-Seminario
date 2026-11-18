"""Paso 3 del Agente de Validación y Remediación: el oráculo determinista decide si hubo fuga (RF06).

No usa red ni modelo: recibe un par (línea base y cruce) y su hipótesis, y devuelve un veredicto.
  - confirmado: la sesión de prueba recibió un dato que solo puede ser del dueño;
  - descartado: la aplicación negó el acceso o respondió sin datos del dueño;
  - dudoso: no se pudo probar, o el oráculo no tiene con qué decidir (queda para el Proyecto de Título).

Dos formas de confirmar, según lo que fijó el Analista en la hipótesis:
  - canario: el valor sembrado (p. ej. Canario-A-E523233E) aparece literal en la respuesta del cruce.
    Es aleatorio, así que no puede aparecer por casualidad;
  - inventario: la marca del dueño (su id o su correo) aparece en el cruce en el MISMO campo JSON donde
    venía en la línea base, con el valor completo. No se busca como texto: en la evidencia del 14 de
    noviembre, el id "26" aparecía dentro de la fecha "2026-11-14" de respuestas que no eran de esa cuenta.
"""
import json

from prototipo.modelos import Hipotesis, ParCruzado, Veredicto


def _exitosa(estado: int | None) -> bool:
    return estado is not None and 200 <= estado < 300


def _hojas(dato, prefijo=""):
    """{"data": {"UserId": 25, "Products": [{"id": 1}]}} -> ("data.UserId", 25), ("data.Products[].id", 1).

    Las posiciones de las listas no se guardan, para que el orden de los elementos no importe.
    """
    if isinstance(dato, dict):
        for k, v in dato.items():
            yield from _hojas(v, f"{prefijo}.{k}" if prefijo else str(k))
    elif isinstance(dato, list):
        for v in dato:
            yield from _hojas(v, f"{prefijo}[]")
    else:
        yield prefijo, dato


def campos_con(texto: str, marca: str) -> set[str] | None:
    """Campos JSON cuyo valor es exactamente la marca. Devuelve None si el texto no es JSON."""
    try:
        dato = json.loads(texto)
    except ValueError:
        return None
    return {campo for campo, v in _hojas(dato)
            if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v) == marca}


def juzgar(par: ParCruzado, h: Hipotesis) -> Veredicto:
    def veredicto(clase, motivo, evidencia="", por="regla") -> Veredicto:
        return Veredicto(hipotesis=h.id, tipo=h.tipo, endpoint=h.endpoint, clase=clase, motivo=motivo,
                         evidencia=evidencia, decidido_por=por)

    # 1. ¿Se pudo probar?
    if par.omitida or par.base is None or par.cruce is None:
        return veredicto("dudoso", "no_ejecutada", par.omitida or "")
    if par.base.error or par.cruce.error:
        return veredicto("dudoso", "error_de_red", par.base.error or par.cruce.error or "")
    if not _exitosa(par.base.estado):
        return veredicto("dudoso", "linea_base_invalida", f"el dueño recibió {par.base.estado}")

    acceso = _exitosa(par.cruce.estado)
    recibido = f"la sesión de prueba recibió {par.cruce.estado}"

    def sin_fuga(por: str) -> Veredicto:
        if not acceso:
            return veredicto("descartado", "acceso_denegado", recibido, por)
        if par.cruce.recortado:  # no se revisó la respuesta completa
            return veredicto("dudoso", "respuesta_recortada", recibido)
        return veredicto("descartado", "respuesta_sin_datos_del_dueno", recibido, por)

    # 2. Oráculo según la verificación que fijó el Analista
    if h.verificacion == "canario":
        if not h.canario or h.canario not in par.base.cuerpo:
            return veredicto("dudoso", "linea_base_sin_canario")
        if h.canario in par.cruce.cuerpo:
            return veredicto("confirmado", "canario_del_dueno", h.canario, "canario")
        return sin_fuga("canario")

    if h.verificacion == "inventario":
        campos = campos_con(par.base.cuerpo, h.marca_dueno) if h.marca_dueno else None
        if not campos:
            return veredicto("dudoso", "linea_base_sin_marca")
        en_cruce = campos_con(par.cruce.cuerpo, h.marca_dueno)
        if en_cruce is None:  # el cruce no es JSON (o llegó recortado)
            if not acceso:
                return veredicto("descartado", "acceso_denegado", recibido, "inventario")
            return veredicto("dudoso", "respuesta_no_json", recibido)
        comunes = sorted(campos & en_cruce)
        if comunes:
            return veredicto("confirmado", "marca_del_dueno_en_el_mismo_campo",
                             f"{comunes[0]} = {h.marca_dueno}", "inventario")
        return sin_fuga("inventario")

    # "sin_verificacion": el objeto lo decidió el LLM y no hay canario ni inventario con que confirmarlo
    if not acceso:
        return veredicto("descartado", "acceso_denegado", recibido)
    return veredicto("dudoso", "requiere_llm", recibido)
