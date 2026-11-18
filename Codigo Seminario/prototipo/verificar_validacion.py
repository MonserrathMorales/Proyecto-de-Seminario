"""Agente de Validación y Remediación: prueba los pasos 1 a 4 y, con --completo, el grafo entero.

Parte 1 (siempre): no necesita Juice Shop, Ollama ni navegador. Copia la evidencia más reciente del
    Explorador a una carpeta temporal (no modifica datos/), genera las hipótesis en modo solo reglas y
    las valida contra una aplicación SIMULADA que contesta con las respuestas guardadas: entrega la
    canasta a cualquier cuenta (la falla documentada de Juice Shop) y protege todo lo demás.
Parte 2 (--completo): ejecuta el grafo explorador -> analista -> validacion -> cerrar contra Juice Shop.
    Necesita Juice Shop recién reiniciado; Ollama solo si quedan candidatos pendientes.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_validacion.py
    python verificar_validacion.py --completo
"""
import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from prototipo.analista import analizar
from prototipo.cruce import cruzar, enviar, ruta_relativa
from prototipo.juice_shop import SesionPreparada
from prototipo.modelos import (Alcance, Hipotesis, ParCruzado, PeticionCapturada, Respuesta, ResultadoAnalisis,
                               ResultadoExploracion, ResultadoValidacion)
from prototipo.oraculo import juzgar
from prototipo.validacion import emitir_veredictos, ruta_salida, validar
from simulacion import AplicacionSimulada, RespuestaSimulada


def imprimir(v: ResultadoValidacion, hipotesis: list[Hipotesis]) -> None:
    por_id = {h.id: h for h in hipotesis}
    print(f" {'Id':<6}{'Tipo':<11}{'Endpoint':<30}{'Valor':<6}{'Prueba':<9}{'Veredicto':<12}{'Motivo'}")
    for x in v.veredictos:
        h = por_id[x.hipotesis]
        print(f" {x.hipotesis:<6}{x.tipo:<11}{x.endpoint[:29]:<30}{h.valor or '-':<6}{h.sesion_prueba:<9}"
              f"{x.clase:<12}{x.motivo}" + (f"  [{x.evidencia}]" if x.clase == "confirmado" else ""))
    print(f"\n Resumen: {v.resumen}   Peticiones enviadas: {v.enviadas}   Omitidas: {v.omitidas or 'ninguna'}")
    for x in v.veredictos:
        if x.remediacion:
            print(f" Corrección sugerida para {x.hipotesis} ({x.remediacion.cwe}): {x.remediacion.recomendacion[:95]}...")


# ---------- Parte 1: sin servicios ----------
archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
print(f"Parte 1. Evidencia: {archivo} (se trabaja sobre una copia temporal)\n")

with tempfile.TemporaryDirectory() as tmp:
    shutil.copy(archivo, Path(tmp) / "exploracion.json")
    r = ResultadoExploracion.model_validate_json((Path(tmp) / "exploracion.json").read_text(encoding="utf-8"))
    analizar(Path(tmp) / "exploracion.json", "solo_reglas")
    ruta_analisis = Path(tmp) / "analisis_solo_reglas.json"
    a = ResultadoAnalisis.model_validate_json(ruta_analisis.read_text(encoding="utf-8"))

    tokens = {c.nombre: f"TOKEN-SIMULADO-{c.nombre}" for c in r.cuentas}
    sesiones = {c.nombre: SesionPreparada(cuenta=c, token=tokens[c.nombre]) for c in r.cuentas}
    app = AplicacionSimulada(r, alcance.url_base, tokens)

    v = validar(ruta_analisis, alcance, sesiones, http=app, pausa=0)
    guardado = ruta_salida(ruta_analisis).read_text(encoding="utf-8")
    imprimir(v, a.hipotesis)

    # Autorización vencida: no debe enviarse nada
    vencido = alcance.model_copy(update={"vigencia_hasta": date.today() - timedelta(days=1)})
    antes = len(app.llamadas)
    try:
        validar(ruta_analisis, vencido, sesiones, http=app, pausa=0)
        detuvo_vencido = False
    except RuntimeError:
        detuvo_vencido = len(app.llamadas) == antes

peticiones = {p.id: p for p in r.peticiones}
por_id = {h.id: h for h in a.hipotesis}
observadas = {ruta_relativa(p) for p in r.peticiones if p.sesion in ("A", "B")}
bases = {(ruta_relativa(peticiones[h.peticion_origen]), h.sesion_origen) for h in a.hipotesis}
cruces = {(ruta_relativa(peticiones[h.peticion_origen]), h.sesion_prueba) for h in a.hipotesis}
canastas = [x for x in v.veredictos if "basket" in x.endpoint and x.tipo == "horizontal"]
resto = [x for x in v.veredictos if x not in canastas]

# Peticiones que la guardia debe rechazar sin enviarlas
host = urlsplit(alcance.url_base).netloc
prohibidas = {
    "metodo_no_permitido": PeticionCapturada(id="X-1", sesion="A", host=host, metodo="POST", ruta="/api/BasketItems",
                                             estado=200, autenticada=True),
    "fuera_del_alcance": PeticionCapturada(id="X-2", sesion="A", host="otro-servidor.example:80", metodo="GET",
                                           ruta="/api/Addresss/7", estado=200, autenticada=True),
    "fuera_de_prefijos": PeticionCapturada(id="X-3", sesion="A", host=host, metodo="GET", ruta="/ftp/acquisitions.md",
                                           estado=200, autenticada=True),
    "origen_no_exitoso": PeticionCapturada(id="X-4", sesion="A", host=host, metodo="GET", ruta="/api/Addresss/7",
                                           estado=500, autenticada=True),
}


def hip(ident: str, peticion: str, prueba: str = "B", **extra) -> Hipotesis:
    datos = dict(id=ident, tipo="horizontal", endpoint="GET /prueba/{id}", peticion_origen=peticion, sesion_origen="A",
                 sesion_prueba=prueba, cuenta_duena="A", origen="regla", verificacion="sin_verificacion")
    return Hipotesis(**{**datos, **extra})


una_de_a = next(h.peticion_origen for h in a.hipotesis if h.sesion_origen == "A")
extras = [hip(f"X-{m}", p.id) for m, p in prohibidas.items()] + [hip("X-duena", una_de_a, prueba="A")]
antes = len(app.llamadas)
_, enviadas_x, omitidas_x = cruzar(extras, {**peticiones, **{p.id: p for p in prohibidas.values()}}, alcance,
                                   sesiones, app, 0)
guardia_ok = (enviadas_x == 0 and len(app.llamadas) == antes
              and omitidas_x == {**{m: 1 for m in prohibidas}, "prueba_con_la_duena": 1})

# Tokens vencidos: la línea base falla y nada debe quedar como "protegido"
vencida = AplicacionSimulada(r, alcance.url_base, tokens, modo="tokens_vencidos")
pares_v, _, _ = cruzar(a.hipotesis, peticiones, alcance, sesiones, vencida, 0)
veredictos_v = emitir_veredictos(pares_v, a.hipotesis)

# Trampa de la subcadena: "26" aparece en la fecha y en un texto, pero el dueño del objeto recibido es 25
h_marca = hip("X-marca", una_de_a, verificacion="inventario", marca_dueno="26")
par_trampa = ParCruzado(hipotesis="X-marca", sesion_base="A", sesion_prueba="B",
                        base=Respuesta(estado=200, cuerpo='{"data": {"id": 7, "UserId": 26}}'),
                        cruce=Respuesta(estado=200, cuerpo='{"data": {"id": 6, "UserId": 25, "nota": "pedido 26", '
                                                           '"createdAt": "2026-11-14T17:16:51.462Z"}}'))
par_fuga = par_trampa.model_copy(update={"cruce": Respuesta(estado=200, cuerpo='{"data": {"id": 7, "UserId": 26}}')})

# Canario: la fuga se confirma aunque la aplicación responda con un código de error
h_canario = hip("X-canario", una_de_a, verificacion="canario", canario="Canario-A-0123ABCD")
con_canario = Respuesta(estado=200, cuerpo='{"data": {"fullName": "Titular Canario-A-0123ABCD"}}')
par_canario = ParCruzado(hipotesis="X-canario", sesion_base="A", sesion_prueba="B", base=con_canario,
                         cruce=con_canario.model_copy(update={"estado": 500}))
par_sin_canario = par_canario.model_copy(update={"cruce": Respuesta(estado=200, cuerpo='{"data": []}')})


class Eco:  # aplicación que devuelve el token en un campo con nombre inocente
    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        return RespuestaSimulada(200, json.dumps({"eco": headers.get("Authorization", ""), "token": "abc"}))


eco = enviar(alcance.url_base + "/rest/eco", sesiones["A"], list(tokens.values()), Eco())

criterios = {
    "Solo se envían GET a la URL base del alcance, sin seguir redirecciones": all(
        ll["url"].startswith(alcance.url_base.rstrip("/") + "/") and ll["redirecciones"] is False
        for ll in app.llamadas),
    "Solo se repiten peticiones que el Explorador observó, sin cambiar ningún identificador": {
        ll["ruta"] for ll in app.llamadas} <= observadas,
    "Cada hipótesis se envía una vez con el dueño (línea base) y una con la sesión de prueba":
        {(ll["ruta"], ll["sesion"]) for ll in app.llamadas[:v.enviadas]} == bases | cruces
        and v.enviadas == len(bases) + len(a.hipotesis),
    "Las pruebas sin sesión no llevan ninguna credencial": all(
        ll["cabeceras"] == {} for ll in app.llamadas if ll["sesion"] == "anonima"),
    "La canasta de otra cuenta queda confirmada por el campo del dueño": len(canastas) == 2 and all(
        x.clase == "confirmado" and x.motivo == "marca_del_dueno_en_el_mismo_campo" for x in canastas),
    "Lo protegido y lo pedido sin sesión queda descartado, sin dudosos": bool(resto) and all(
        x.clase == "descartado" for x in resto),
    "Solo los hallazgos confirmados llevan corrección sugerida (CWE-639)": all(
        (x.remediacion is not None and x.remediacion.cwe == "CWE-639") == (x.clase == "confirmado")
        for x in v.veredictos),
    "La guardia rechaza escrituras, otros servidores, otras rutas y orígenes fallidos sin enviar nada": guardia_ok,
    "Con la autorización vencida no se envía ninguna petición": detuvo_vencido,
    "Con los tokens vencidos todo queda dudoso y nada se da por protegido": bool(veredictos_v) and all(
        x.clase == "dudoso" and x.motivo == "linea_base_invalida" for x in veredictos_v),
    "La marca del dueño no se busca como texto: '26' dentro de '2026' no confirma una fuga":
        juzgar(par_trampa, h_marca).clase == "descartado" and juzgar(par_fuga, h_marca).clase == "confirmado",
    "El canario confirma la fuga aunque el código sea de error, y su ausencia la descarta":
        juzgar(par_canario, h_canario).motivo == "canario_del_dueno"
        and juzgar(par_sin_canario, h_canario).clase == "descartado",
    "La evidencia guardada no contiene tokens": "TOKEN-SIMULADO" not in guardado and "Bearer" not in guardado
        and "TOKEN-SIMULADO" not in eco.cuerpo and '"token": "***"' in eco.cuerpo,
    "La validación se guarda y se lee sin pérdida": ResultadoValidacion.model_validate_json(guardado) == v,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Parte 2: grafo completo ----------
if "--completo" in sys.argv:
    from prototipo.grafo import SESIONES, construir
    print("\nParte 2. Grafo completo: explorador -> analista -> validacion -> cerrar (se abre el navegador)...")
    grafo = construir()
    config = {"configurable": {"thread_id": "validacion"}}
    estado = grafo.invoke({"ruta_alcance": "alcance_juice.json"}, config)
    for e in estado["registro"]:
        extra = {k: x for k, x in e.items() if k not in ("etapa", "inicio", "duracion_s", "resultado")}
        print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>6} s  {extra}")
    if estado.get("error") or "ruta_validacion" not in estado:
        raise SystemExit(f"\n[FALLA] El flujo no llegó a validar: {estado.get('error')}")

    texto = Path(estado["ruta_validacion"]).read_text(encoding="utf-8")
    real = ResultadoValidacion.model_validate_json(texto)
    hipotesis = ResultadoAnalisis.model_validate_json(Path(estado["ruta_analisis"]).read_text(encoding="utf-8")).hipotesis
    print()
    imprimir(real, hipotesis)
    punto_control = json.dumps(grafo.get_state(config).values, default=str)
    criterios = {
        "El grafo ejecutó explorador, analista, validacion y cerrar sin intervención":
            [e["etapa"] for e in estado["registro"]] == ["explorador", "analista", "validacion", "cerrar"],
        "Se confirmó al menos una falla de lectura (criterio de la sección 8.4)": real.resumen.get("confirmado", 0) >= 1,
        "Todo hallazgo confirmado trae su corrección sugerida": all(
            x.remediacion is not None for x in real.veredictos if x.clase == "confirmado"),
        "No se enviaron más peticiones que dos por hipótesis": real.enviadas <= 2 * len(hipotesis),
        "Ni la evidencia ni el estado del grafo contienen tokens": all(
            s not in t for s in ("Bearer", "eyJ") for t in (texto, punto_control)),
        "Las sesiones se liberaron de la memoria al cerrar": estado.get("ejecucion") not in SESIONES,
    }
    print()
    for nombre, ok in criterios.items():
        print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
    print(f"\nEvidencia en {Path(estado['ruta_validacion']).parent}")
