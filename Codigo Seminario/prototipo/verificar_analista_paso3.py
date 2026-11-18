"""Paso 3 del Analista: resuelve con el inventario la propiedad de los candidatos.

No necesita Juice Shop ni Ollama. Hace tres cosas:
  1. Resuelve los candidatos de la evidencia más reciente del Explorador.
  2. Prueba casos pequeños, incluida la colisión del id 7 y un id en el cuerpo (caso J35 del 13/11).
  3. Si encuentra casos_juice.json, mide cuántos de los 23 casos etiquetados resuelve el inventario
     y cuáles quedarían para el LLM (paso 4).
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_analista_paso3.py
"""
import json
from pathlib import Path

from prototipo.extraccion import candidatos_de, extraer
from prototipo.modelos import ObjetoSembrado, PeticionCapturada, ResultadoExploracion
from prototipo.propiedad import Inventario, resolver

archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
r = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
inventario = Inventario(r.inventario)
candidatos = resolver(extraer(r.peticiones), inventario)
canarios = {(o.tipo, o.id, o.cuenta): o.canario for o in r.inventario}

print(f"Evidencia: {archivo}")
if inventario.uso_respaldo:
    print("Aviso: esta evidencia es anterior al cambio del inventario; el endpoint de cada objeto se tomó del adaptador.")
print(f"\n {'Sesión':<7}{'Endpoint':<28}{'Valor':<7}{'Decidido por':<14}{'Dueño':<7}{'Objeto':<11}{'Canario'}")
for c in candidatos:
    can = canarios.get((c.objeto, c.valor, c.cuenta_duena)) or "-"
    print(f" {c.sesion:<7}{c.endpoint:<28}{c.valor:<7}{c.decidido_por or 'pendiente':<14}"
          f"{c.cuenta_duena or '-':<7}{c.objeto or '-':<11}{can}")
resueltos = [c for c in candidatos if c.decidido_por == "inventario"]
print(f"\nResueltos por el inventario: {len(resueltos)} de {len(candidatos)}; pendientes para el paso 4: "
      f"{len(candidatos) - len(resueltos)}")

# ---------- Casos pequeños ----------
inv_prueba = Inventario([
    ObjetoSembrado(cuenta="A", tipo="direccion", id="7", endpoint="/api/Addresss/{id}", canario="Canario-A-X"),
    ObjetoSembrado(cuenta="B", tipo="canasta", id="7", endpoint="/rest/basket/{id}"),
    ObjetoSembrado(cuenta="A", tipo="canasta", id="6", endpoint="/rest/basket/{id}")])


def resolver_uno(sesion, metodo, ruta, consulta="", cuerpo=""):
    p = PeticionCapturada(id="T", sesion=sesion, metodo=metodo, ruta=ruta, consulta=consulta,
                          cuerpo_peticion=cuerpo, estado=200, autenticada=True)
    return {c.parametro: c for c in resolver(candidatos_de(p), inv_prueba)}


canasta_b = resolver_uno("B", "GET", "/rest/basket/7")["basket"]
direccion_a = resolver_uno("A", "GET", "/api/Addresss/7")["Addresss"]
cuerpo = resolver_uno("A", "POST", "/api/BasketItems", cuerpo='{"ProductId": 2, "BasketId": "6"}')
criterios = {
    "Cada candidato resuelto tiene dueño y tipo de objeto": all(c.cuenta_duena and c.objeto for c in resueltos),
    "En la navegación normal, cada objeto pertenece a la sesión que lo pidió":
        all(c.cuenta_duena == c.sesion for c in resueltos),
    "Colisión del id 7: canasta de B y dirección de A, sin confundirlas":
        (canasta_b.objeto, canasta_b.cuenta_duena) == ("canasta", "B")
        and (direccion_a.objeto, direccion_a.cuenta_duena) == ("direccion", "A"),
    "Un id en el cuerpo se resuelve por su nombre (BasketId, caso J35)":
        (cuerpo["BasketId"].objeto, cuerpo["BasketId"].cuenta_duena) == ("canasta", "A"),
    "Lo que no está en el inventario queda pendiente (ProductId)": cuerpo["ProductId"].decidido_por is None,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Medición contra los 23 casos etiquetados ----------
etiquetados = next((p for p in (Path("casos_juice.json"), Path("..") / "casos_juice.json") if p.exists()), None)
if etiquetados is None:
    print("\n(No se encontró casos_juice.json; se omite la medición contra casos etiquetados.)")
else:
    # Inventario de la captura del 13 de noviembre, reconstruido de las respuestas de esa captura
    inv_13 = Inventario([ObjetoSembrado(cuenta=c, tipo=t, id=i) for c, t, i in [
        ("A", "usuario", "25"), ("A", "canasta", "6"), ("A", "direccion", "7"), ("A", "tarjeta", "7"),
        ("B", "usuario", "26"), ("B", "canasta", "7"), ("B", "direccion", "8"), ("B", "tarjeta", "8")]])
    casos = json.loads(etiquetados.read_text(encoding="utf-8"))["casos"]
    por_inventario, para_llm, sobrantes = [], [], 0
    for caso in casos:
        linea, _, cuerpo_txt = caso["peticion"].partition("  cuerpo: ")
        metodo, url = linea.split(" ", 1)
        ruta, _, consulta = url.partition("?")
        p = PeticionCapturada(id=caso["id"], sesion=caso["sesion"], metodo=metodo, ruta=ruta, consulta=consulta,
                              cuerpo_peticion=cuerpo_txt, estado=200, autenticada=True)
        esp = caso["esperado"]
        for c in resolver(candidatos_de(p), inv_13):
            es_el_esperado = esp["contiene_identificador"] and (c.ubicacion, c.valor) == (esp["ubicacion"], esp["valor"])
            if c.decidido_por == "inventario":
                por_inventario.append((caso["id"], c, esp["cuenta_duena"]))
            elif es_el_esperado:
                para_llm.append(caso["id"])
            else:
                sobrantes += 1
    n_pos = sum(c["esperado"]["contiene_identificador"] for c in casos)
    print(f"\nMedición contra {len(casos)} casos etiquetados ({etiquetados})")
    print(f"   Identificadores resueltos por el inventario: {len(por_inventario)} de {n_pos}")
    for cid, c, etiqueta in por_inventario:
        nota = "" if etiqueta == c.cuenta_duena else f"   (la etiqueta decía '{etiqueta}': el modelo no podía saberlo)"
        print(f"      {cid}: {c.ubicacion:<8} {c.parametro:<10} = {c.valor:<3} -> {c.objeto} de {c.cuenta_duena}{nota}")
    print(f"   Identificadores que quedan para el LLM (paso 4): {len(para_llm)}  {para_llm}")
    print(f"   Candidatos sobrantes que también decidirá el LLM: {sobrantes}")
