"""Pasos 1 y 2 del Agente de Validación y Remediación: guardia de alcance y envío de los cruces.

Por cada hipótesis se repite la petición ORIGINAL, sin cambiarle nada, dos veces:
  - línea base: con la sesión del dueño, para comprobar que el objeto sigue disponible. Sin ella,
    un token vencido se leería como "la aplicación protege el objeto";
  - cruce: con la sesión de prueba (la otra cuenta, o ninguna).

Límites fijados en el código (RF01, RNF02):
  - solo GET, y solo peticiones que el Explorador observó y que respondieron bien;
  - solo hacia la URL base del alcance y bajo sus prefijos de API;
  - la ruta y la consulta se copian tal cual: no se cambia ni se prueba ningún identificador nuevo;
  - sin seguir redirecciones, con una pausa entre peticiones y un tope de hipótesis por ejecución.
Este paso no interpreta las respuestas: eso lo hace el oráculo (paso 3).
"""
import time
from urllib.parse import urlsplit

import requests

from prototipo import juice_shop as adaptador
from prototipo.filtro import OCULTO, ocultar_secretos
from prototipo.juice_shop import SesionPreparada
from prototipo.modelos import Alcance, Hipotesis, ParCruzado, PeticionCapturada, Respuesta

METODOS_PERMITIDOS = {"GET"}
TIEMPO_ESPERA = 10      # segundos por petición
PAUSA = 0.5             # segundos entre peticiones, para no cargar la aplicación
MAX_CUERPO = 200_000    # caracteres de la respuesta que se guardan
MAX_HIPOTESIS = 200     # tope de seguridad por ejecución


def guardia(origen: PeticionCapturada, alcance: Alcance) -> str | None:
    """Devuelve por qué NO se puede repetir una petición, o None si está dentro de los límites."""
    if origen.metodo.upper() not in METODOS_PERMITIDOS:
        return "metodo_no_permitido"
    if origen.host and origen.host != urlsplit(alcance.url_base).netloc:
        return "fuera_del_alcance"
    if (not origen.ruta.startswith("/") or ".." in origen.ruta.split("/")
            or not origen.ruta.startswith(tuple(alcance.prefijos_api))):
        return "fuera_de_prefijos"
    if not 200 <= origen.estado < 300:
        return "origen_no_exitoso"
    return None


def ruta_relativa(origen: PeticionCapturada) -> str:
    return origen.ruta + (f"?{origen.consulta}" if origen.consulta else "")


def url_de(origen: PeticionCapturada, alcance: Alcance) -> str:
    """Arma la URL siempre desde la URL base del alcance y comprueba que no apunte a otro servidor."""
    url = alcance.url_base.rstrip("/") + ruta_relativa(origen)
    if urlsplit(url).netloc != urlsplit(alcance.url_base).netloc:
        raise RuntimeError(f"La petición {origen.id} apuntaría fuera del alcance; no se envía.")
    return url


def enviar(url: str, sesion: SesionPreparada | None, secretos: list[str], http=requests) -> Respuesta:
    """Hace un GET con la sesión indicada (None = sin autenticación) y devuelve la respuesta sin secretos."""
    inicio = time.perf_counter()

    def ms() -> int:
        return round((time.perf_counter() - inicio) * 1000)

    try:
        r = http.get(url, headers=adaptador.cabeceras(sesion), timeout=TIEMPO_ESPERA, allow_redirects=False)
    except requests.RequestException as e:
        return Respuesta(duracion_ms=ms(), error=f"{type(e).__name__}: {e}"[:200])
    cuerpo = ocultar_secretos(r.text or "")
    for secreto in secretos:  # por si la aplicación devuelve el token en un campo con otro nombre
        cuerpo = cuerpo.replace(secreto, OCULTO)
    return Respuesta(estado=r.status_code, tipo_contenido=r.headers.get("content-type", ""),
                     cuerpo=cuerpo[:MAX_CUERPO], recortado=len(cuerpo) > MAX_CUERPO, duracion_ms=ms())


def cruzar(hipotesis: list[Hipotesis], peticiones: dict[str, PeticionCapturada], alcance: Alcance,
           sesiones: dict[str, SesionPreparada], http=requests, pausa: float = PAUSA
           ) -> tuple[list[ParCruzado], int, dict[str, int]]:
    """Ejecuta las hipótesis. Devuelve los pares, cuántas peticiones se enviaron y las omitidas por motivo."""
    if len(hipotesis) > MAX_HIPOTESIS:
        raise RuntimeError(f"Hay {len(hipotesis)} hipótesis y el tope por ejecución es {MAX_HIPOTESIS}. "
                           f"No se envía ninguna: revisa el análisis antes de subir el tope.")
    secretos = [s.token for s in sesiones.values() if s.token]
    pares, omitidas, enviadas = [], {}, 0
    bases: dict[tuple[str, str], Respuesta] = {}  # una línea base por petición original y dueño

    for h in hipotesis:
        origen = peticiones.get(h.peticion_origen)
        if origen is None:
            motivo = "origen_desconocido"
        elif h.sesion_prueba == h.cuenta_duena:
            motivo = "prueba_con_la_duena"  # no sería un cruce: la dueña pidiendo su propio objeto
        elif h.sesion_origen not in sesiones or (h.sesion_prueba != "anonima" and h.sesion_prueba not in sesiones):
            motivo = "sin_sesion_disponible"
        else:
            motivo = guardia(origen, alcance)
        if motivo:
            omitidas[motivo] = omitidas.get(motivo, 0) + 1
            pares.append(ParCruzado(hipotesis=h.id, sesion_base=h.sesion_origen, sesion_prueba=h.sesion_prueba,
                                    omitida=motivo))
            continue

        url = url_de(origen, alcance)
        clave = (h.peticion_origen, h.sesion_origen)
        if clave not in bases:
            bases[clave] = enviar(url, sesiones[h.sesion_origen], secretos, http)
            enviadas += 1
            time.sleep(pausa)
        sesion_prueba = None if h.sesion_prueba == "anonima" else sesiones[h.sesion_prueba]
        cruce = enviar(url, sesion_prueba, secretos, http)
        enviadas += 1
        time.sleep(pausa)
        pares.append(ParCruzado(hipotesis=h.id, metodo=origen.metodo, ruta=ruta_relativa(origen),
                                sesion_base=h.sesion_origen, sesion_prueba=h.sesion_prueba,
                                base=bases[clave], cruce=cruce))
    return pares, enviadas, omitidas
