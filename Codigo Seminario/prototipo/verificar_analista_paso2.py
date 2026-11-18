"""Paso 2 del Analista: extrae candidatos con reglas y los compara con casos ya etiquetados.

No necesita Juice Shop ni Ollama. Hace tres cosas:
  1. Extrae candidatos de la evidencia más reciente del Explorador.
  2. Prueba las reglas con casos pequeños, incluidos los errores de los modelos el 13 de noviembre.
  3. Si encuentra casos_juice.json (en esta carpeta o en la de arriba), mide las reglas contra
     los 23 casos etiquetados a mano.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_analista_paso2.py
"""
import json
from pathlib import Path

from prototipo.extraccion import candidatos_de, extraer
from prototipo.modelos import PeticionCapturada, ResultadoExploracion

archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
r = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
candidatos = extraer(r.peticiones)
por_id = {p.id: p for p in r.peticiones}

print(f"Evidencia: {archivo}\nCandidatos extraídos: {len(candidatos)}\n")
print(f" {'Sesión':<7}{'Endpoint':<30}{'Ubicación':<11}{'Parámetro':<14}{'Valor'}")
for c in candidatos:
    print(f" {c.sesion:<7}{c.endpoint:<30}{c.ubicacion:<11}{c.parametro:<14}{c.valor}")


def pet(metodo, ruta, consulta="", cuerpo="", respuesta="{}"):
    return PeticionCapturada(id="T", sesion="A", metodo=metodo, ruta=ruta, consulta=consulta, cuerpo_peticion=cuerpo,
                             estado=200, cuerpo_respuesta=respuesta, autenticada=True)


def valores(p):
    return {(c.ubicacion, c.valor) for c in candidatos_de(p)}


def en_su_peticion(c):
    p = por_id[c.peticion]
    return c.valor in {"ruta": p.ruta, "consulta": p.consulta, "cuerpo": p.cuerpo_peticion}[c.ubicacion]


criterios = {
    "Todo candidato sale de su propia petición, no de la respuesta": all(en_su_peticion(c) for c in candidatos),
    "Canastas y direcciones de A y B son candidatas": {("A", "6"), ("B", "7")} <= {
        (c.sesion, c.valor) for c in candidatos if "basket" in c.endpoint} and {("A", "7"), ("B", "8")} <= {
        (c.sesion, c.valor) for c in candidatos if "Addresss/{id}" in c.endpoint},
    "La sesión anónima no genera candidatos": all(c.sesion in ("A", "B") for c in candidatos),
    "Un id solo en la respuesta no es candidato (error J26 del 13/11)":
        valores(pet("GET", "/api/Cards", respuesta='{"data":[{"id":8,"UserId":26}]}')) == set(),
    "Paginación y búsquedas no son candidatos (caso C3)":
        valores(pet("GET", "/api/productos", "pagina=2&tamano=20")) == set()
        and valores(pet("GET", "/rest/products/search", "q=")) == set(),
    "Se detectan ids en consulta y cuerpo, y UUID en la ruta":
        ("consulta", "3") in valores(pet("GET", "/api/Products/", "id=3"))
        and ("cuerpo", "6") in valores(pet("POST", "/api/BasketItems", cuerpo='{"ProductId":2,"BasketId":"6"}'))
        and ("ruta", "3f2b9c1e-7a4d-4e8b-9c2f-5d1a6b7e8f90") in valores(
            pet("GET", "/api/documentos/3f2b9c1e-7a4d-4e8b-9c2f-5d1a6b7e8f90")),
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Medición contra los 23 casos etiquetados ----------
etiquetados = next((p for p in (Path("casos_juice.json"), Path("..") / "casos_juice.json") if p.exists()), None)
if etiquetados is None:
    print("\n(No se encontró casos_juice.json; se omite la medición contra casos etiquetados.)")
else:
    casos = json.loads(etiquetados.read_text(encoding="utf-8"))["casos"]
    print(f"\nMedición contra {len(casos)} casos etiquetados ({etiquetados})")
    acierto_pos = acierto_neg = n_pos = n_neg = extra = 0
    for caso in casos:
        linea, _, cuerpo = caso["peticion"].partition("  cuerpo: ")
        metodo, url = linea.split(" ", 1)
        ruta, _, consulta = url.partition("?")
        encontrados = valores(pet(metodo, ruta, consulta, cuerpo))
        esp = caso["esperado"]
        if esp["contiene_identificador"]:
            n_pos += 1
            ok = (esp["ubicacion"], esp["valor"]) in encontrados
            acierto_pos += ok
            otros = encontrados - {(esp["ubicacion"], esp["valor"])}
            if otros:
                extra += len(otros)
                print(f"   {caso['id']}: además del identificador esperado, {sorted(otros)} (lo resuelven los pasos 3 y 4)")
        else:
            n_neg += 1
            ok = not encontrados
            acierto_neg += ok
        if not ok:
            print(f"   revisar {caso['id']}: {caso['peticion'][:60]} -> {sorted(encontrados) or 'sin candidatos'}")
    print(f"   Con identificador: {acierto_pos} de {n_pos} incluyen el identificador correcto entre sus candidatos")
    print(f"   Sin identificador: {acierto_neg} de {n_neg} no generan candidatos")
    print(f"   Candidatos adicionales por resolver: {extra}")
