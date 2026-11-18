"""Paso 5 del Analista: convierte los candidatos decididos en hipótesis para el Agente de Validación y Remediación.

Dos tipos de hipótesis (variantes de la sección 2.1 del informe):
  - horizontal: repetir la petición del dueño con la sesión de la otra cuenta (IDOR/BOLA);
  - sin_sesion: repetir la petición del dueño sin autenticación (acceso sin sesión).
La variante vertical (BFLA) requiere una cuenta de administrador y se aborda en el Proyecto de Título.

En esta etapa solo se generan pruebas de LECTURA (GET): las escrituras quedan para el Proyecto,
según la prioridad del Anexo E, y se cuentan como omitidas.
"""
import re

from prototipo.endpoints import agrupar
from prototipo.modelos import Candidato, Hipotesis, ResultadoExploracion

OTRA = {"A": "B", "B": "A"}


def _canario_en(texto: str) -> str | None:
    m = re.search(r"Canario-[AB]-[0-9A-F]{8}", texto)
    return m.group(0) if m else None


def generar(r: ResultadoExploracion, candidatos: list[Candidato]) -> tuple[list[Hipotesis], dict[str, int]]:
    peticiones = {p.id: p for p in r.peticiones}
    cuentas = {c.nombre: c for c in r.cuentas}
    canarios = {(o.tipo, o.id, o.cuenta): o.canario for o in r.inventario}
    hipotesis, omitidas, vistas = [], {}, set()

    def omitir(motivo):
        omitidas[motivo] = omitidas.get(motivo, 0) + 1

    def agregar(**datos):
        clave = (datos["tipo"], datos["endpoint"], datos.get("valor"), datos["sesion_prueba"])
        if clave in vistas:
            return
        vistas.add(clave)
        hipotesis.append(Hipotesis(id=f"H-{len(hipotesis) + 1:03d}", **datos))

    # 1. Objetos privados pedidos por identificador
    con_candidato = set()
    pedidos_por_su_duena = {(c.endpoint, c.valor) for c in candidatos if c.cuenta_duena == c.sesion}
    for c in candidatos:
        con_candidato.add(c.endpoint)
        if c.decidido_por is None:
            omitir("error_modelo")  # el modelo no respondió: no se sabe si el objeto es privado
            continue
        if not (c.es_identificador and c.visibilidad == "privado"):
            continue
        if peticiones[c.peticion].metodo != "GET":
            omitir("escritura")
            continue
        if not 200 <= peticiones[c.peticion].estado < 300:
            omitir("origen_no_exitoso")  # si la petición original falló, repetirla no prueba nada
            continue
        if c.cuenta_duena in OTRA and c.cuenta_duena != c.sesion:
            # Lo pidió una cuenta que no es la dueña: cruzar desde ella probaría el objeto con su propia dueña.
            # La prueba válida sale de la petición de la dueña, si existe.
            if (c.endpoint, c.valor) not in pedidos_por_su_duena:
                omitir("sin_linea_base_del_dueno")
            continue
        canario = canarios.get((c.objeto, c.valor, c.cuenta_duena))
        if c.decidido_por == "inventario":
            verificacion = "canario" if canario else "inventario"
            marca = None if canario else cuentas[c.cuenta_duena].id_usuario
        else:  # decidido por el LLM: el oráculo determinista no puede confirmar la fuga
            verificacion, marca = "sin_verificacion", None
        comun = dict(endpoint=c.endpoint, peticion_origen=c.peticion, sesion_origen=c.sesion,
                     cuenta_duena=c.cuenta_duena or "desconocida", parametro=c.parametro, valor=c.valor,
                     ubicacion=c.ubicacion, objeto=c.objeto, origen=c.decidido_por, verificacion=verificacion,
                     canario=canario, marca_dueno=marca)
        agregar(tipo="horizontal", sesion_prueba=OTRA[c.sesion], **comun)
        agregar(tipo="sin_sesion", sesion_prueba="anonima", **comun)

    # 2. Endpoints autenticados sin identificador (p. ej. "mis direcciones"): solo prueba sin sesión,
    #    y solo si la respuesta del dueño contiene datos suyos que permitan confirmar la fuga.
    for e in agrupar(r.peticiones):
        if e.clave in con_candidato or not e.autenticada:
            continue
        p = next((peticiones[i] for i in e.peticiones if peticiones[i].sesion in ("A", "B")
                  and peticiones[i].autenticada), None)
        if p is None:
            continue
        if p.metodo != "GET":
            omitir("escritura")
            continue
        if not 200 <= p.estado < 300:
            omitir("origen_no_exitoso")
            continue
        canario = _canario_en(p.cuerpo_respuesta)
        correo = cuentas[p.sesion].correo
        if canario:
            verificacion, marca = "canario", None
        elif correo in p.cuerpo_respuesta:
            verificacion, marca = "inventario", correo
        else:
            omitir("sin_datos_propios")  # público o vacío: una respuesta sin sesión no probaría nada
            continue
        agregar(tipo="sin_sesion", endpoint=e.clave, peticion_origen=p.id, sesion_origen=p.sesion,
                sesion_prueba="anonima", cuenta_duena=p.sesion, origen="regla", verificacion=verificacion,
                canario=canario, marca_dueno=marca)
    return hipotesis, omitidas
