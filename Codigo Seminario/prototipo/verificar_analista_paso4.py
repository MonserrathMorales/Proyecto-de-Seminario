"""Paso 4 del Analista: el LLM decide los candidatos pendientes; se compara con el modo solo reglas.

Necesita Ollama abierto con gemma4:e4b (no necesita Juice Shop). Hace tres cosas:
  1. Aplica el Analista a la evidencia más reciente del Explorador.
  2. Sobre los 23 casos etiquetados, compara "solo reglas" con "reglas + LLM" (hipótesis H3),
     con 3 repeticiones de cada consulta para observar la estabilidad del modelo.
  3. Libera el modelo de la memoria al terminar.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_analista_paso4.py
Tarda unos 3 minutos.
"""
import json
import statistics
from pathlib import Path

from ollama import ps

from prototipo.clasificador import MODELO, Clasificador, decidir_pendientes, verificar_modelo
from prototipo.extraccion import candidatos_de, extraer
from prototipo.modelos import CuentaExplorada, ObjetoSembrado, PeticionCapturada, ResultadoExploracion
from prototipo.propiedad import Inventario, resolver

REPETICIONES = 3
print("1. Comprobando Ollama y el modelo...")
verificar_modelo()

# ---------- Evidencia del Explorador ----------
archivo = sorted(Path("datos").glob("*/exploracion.json"))[-1]
r = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
clasificador = Clasificador(r.cuentas)
pendientes_evidencia = [c for c in resolver(extraer(r.peticiones), Inventario(r.inventario)) if c.decidido_por is None]
decidir_pendientes(pendientes_evidencia, {p.id: p for p in r.peticiones}, clasificador)
consultas_evidencia = clasificador.consultas
print(f"2. Evidencia {archivo}: {len(pendientes_evidencia)} candidatos pendientes -> {consultas_evidencia} consultas al modelo")

# ---------- Casos etiquetados ----------
etiquetados = next((p for p in (Path("casos_juice.json"), Path("..") / "casos_juice.json") if p.exists()), None)
if etiquetados is None:
    raise SystemExit("No se encontró casos_juice.json (en esta carpeta o en la de arriba).")
datos = json.loads(etiquetados.read_text(encoding="utf-8"))
cuentas = [CuentaExplorada(nombre=n, correo=u["correo"], id_usuario=str(u["id"])) for n, u in datos["usuarios"].items()]
inv_13 = Inventario([ObjetoSembrado(cuenta=c, tipo=t, id=i) for c, t, i in [  # captura del 13 de noviembre
    ("A", "usuario", "25"), ("A", "canasta", "6"), ("A", "direccion", "7"), ("A", "tarjeta", "7"),
    ("B", "usuario", "26"), ("B", "canasta", "7"), ("B", "direccion", "8"), ("B", "tarjeta", "8")]])
peticiones, candidatos, esperado = {}, [], {}
for caso in datos["casos"]:
    linea, _, cuerpo = caso["peticion"].partition("  cuerpo: ")
    metodo, url = linea.split(" ", 1)
    ruta, _, consulta = url.partition("?")
    estado, _, resto = caso["respuesta"].partition(" ")
    cuerpo_resp = resto.split(" ", 1)[1] if resto.startswith(("OK", "Created")) else resto
    p = PeticionCapturada(id=caso["id"], sesion=caso["sesion"], metodo=metodo, ruta=ruta, consulta=consulta,
                          cuerpo_peticion=cuerpo, estado=int(estado), cuerpo_respuesta=cuerpo_resp, autenticada=True)
    peticiones[p.id] = p
    for c in resolver(candidatos_de(p), inv_13):
        candidatos.append(c)
        e = caso["esperado"]
        es_el = e["contiene_identificador"] and (c.ubicacion, c.valor) == (e["ubicacion"], e["valor"])
        esperado[(c.peticion, c.parametro)] = e["visibilidad"] if es_el else "no_es"  # "no_es": candidato sobrante

clasificador = Clasificador(cuentas)
solo_reglas = decidir_pendientes(candidatos, peticiones, None)
repeticiones = [decidir_pendientes(candidatos, peticiones, clasificador) for _ in range(REPETICIONES)]
print(f"3. Casos etiquetados: {len(candidatos)} candidatos, "
      f"{sum(c.decidido_por is None for c in candidatos)} para el modelo, {REPETICIONES} repeticiones")


def privado(c):
    return bool(c.es_identificador) and c.visibilidad == "privado"


print(f"\n {'Caso':<5}{'Parámetro = valor':<20}{'Esperado':<10}{'Respuestas del modelo (3 repeticiones)'}")
estables = 0
for i, c in enumerate(candidatos):
    if c.decidido_por == "inventario":
        continue
    resp = [rep[i] for rep in repeticiones]
    textos = [("id " + (x.visibilidad or "?") + (f"/{x.cuenta_duena}" if x.cuenta_duena else "")) if x.es_identificador
              else ("no es id" if x.decidido_por else "error") for x in resp]
    estables += len(set(textos)) == 1
    print(f" {c.peticion:<5}{(c.parametro + ' = ' + c.valor)[:19]:<20}{esperado[(c.peticion, c.parametro)]:<10}"
          f"{' | '.join(textos)}")

privados_esperados = {k for k, v in esperado.items() if v == "privado"}


def medir(resultado):
    detectados = {(c.peticion, c.parametro) for c in resultado if privado(c)}
    return len(detectados & privados_esperados), len(detectados - privados_esperados)


vp_r, fp_r = medir(solo_reglas)
medidas = [medir(rep) for rep in repeticiones]
n_llm = sum(1 for c in candidatos if c.decidido_por != "inventario")
print(f"\n Identificadores privados detectados (de {len(privados_esperados)} esperados), y falsos privados:")
print(f"   Solo reglas  : {vp_r} detectados, {fp_r} falsos")
for k, (vp, fp) in enumerate(medidas, 1):
    print(f"   Reglas + LLM : {vp} detectados, {fp} falsos   (repetición {k})")
print(f" Respuestas iguales en las {REPETICIONES} repeticiones: {estables} de {n_llm} candidatos")
print(f" Tiempo por consulta: {statistics.mean(clasificador.tiempos):.1f} s de media "
      f"(la primera {clasificador.tiempos[0]:.1f} s, incluye la carga del modelo)")

clasificador.liberar()
cargado = any(m.model.startswith(MODELO) for m in ps().models)
criterios = {
    "Ollama respondió y el modelo existe": True,
    "Con la evidencia actual el modelo no hace falta (0 consultas)": consultas_evidencia == 0,
    "Todas las respuestas del modelo fueron válidas": clasificador.errores == 0,
    "Con el LLM se detectan al menos tantos privados como solo con reglas":
        all(vp >= vp_r for vp, _ in medidas),
    "El modelo se liberó de la memoria al terminar": not cargado,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
