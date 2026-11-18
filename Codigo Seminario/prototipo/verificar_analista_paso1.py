"""Paso 1 del Analista: agrupa por endpoint la evidencia más reciente del Explorador.

No necesita Juice Shop ni Ollama: lee datos/<ejecucion>/exploracion.json.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_analista_paso1.py
"""
from datetime import datetime
from pathlib import Path

from prototipo.endpoints import agrupar, plantilla
from prototipo.modelos import Candidato, Hipotesis, ResultadoAnalisis, ResultadoExploracion

archivos = sorted(Path("datos").glob("*/exploracion.json"))
if not archivos:
    raise SystemExit("No hay evidencia en datos\\. Ejecuta primero el Explorador (verificar_paso5.py o demo_explorador.py).")
archivo = archivos[-1]
r = ResultadoExploracion.model_validate_json(archivo.read_text(encoding="utf-8"))
endpoints = agrupar(r.peticiones)

print(f"Evidencia: {archivo}  ({len(r.peticiones)} peticiones)")
print(f"Endpoints distintos: {len(endpoints)}\n")
print(f" {'Endpoint':<46}{'Peticiones':>11}  {'Sesiones':<16}{'Autenticado'}")
for e in sorted(endpoints, key=lambda e: e.clave):
    print(f" {e.clave:<46}{len(e.peticiones):>11}  {','.join(e.sesiones):<16}{'sí' if e.autenticada else 'no'}")

claves = {e.clave for e in endpoints}
ids_agrupados = [i for e in endpoints for i in e.peticiones]
ejemplo = ResultadoAnalisis(
    ejecucion=r.ejecucion, fecha=datetime.now(), modo="solo_reglas", endpoints=endpoints,
    candidatos=[Candidato(peticion="A-0001", endpoint="GET /rest/basket/{id}", sesion="A", parametro="ruta[2]",
                          valor="6", ubicacion="ruta")],
    hipotesis=[Hipotesis(id="H-001", tipo="horizontal", endpoint="GET /rest/basket/{id}", peticion_origen="A-0001",
                         sesion_origen="A", sesion_prueba="B", cuenta_duena="A", parametro="ruta[2]", valor="6",
                         ubicacion="ruta", objeto="canasta", origen="inventario", verificacion="inventario")])
criterios = {
    "Cada petición quedó en exactamente un endpoint": sorted(ids_agrupados) == sorted(p.id for p in r.peticiones),
    "Las canastas de A y B forman un solo endpoint": "GET /rest/basket/{id}" in claves
        and not any(c.startswith("GET /rest/basket/") and "{id}" not in c for c in claves),
    "Las direcciones de A y B forman un solo endpoint": "GET /api/Addresss/{id}" in claves,
    "Las rutas sin identificador no cambian": plantilla("/rest/languages") == "/rest/languages"
        and plantilla("/rest/admin/application-version") == "/rest/admin/application-version",
    "Se reconocen UUID e identificadores largos": plantilla("/api/doc/3f2b9c1e-7a4d-4e8b-9c2f-5d1a6b7e8f90")
        == "/api/doc/{id}" and plantilla("/api/x/64b7f0c2a1e4d3b2c1a09f8e") == "/api/x/{id}",
    "El formato de salida se guarda y se lee sin pérdida":
        ResultadoAnalisis.model_validate_json(ejemplo.model_dump_json()) == ejemplo,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
