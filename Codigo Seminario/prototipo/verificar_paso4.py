"""Paso 4 del Explorador: ejecuta el Explorador completo y revisa el filtro y la evidencia guardada.

Uso (Juice Shop recién reiniciado; desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_paso4.py
"""
from collections import Counter
from pathlib import Path

from prototipo.explorador import CARPETA_DATOS, explorar
from prototipo.modelos import Alcance, ResultadoExploracion

alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
print("Ejecutando el Explorador (se abre una ventana del navegador)...")
r, sesiones = explorar(alcance)
archivo = CARPETA_DATOS / r.ejecucion / "exploracion.json"

total = len(r.peticiones) + sum(r.descartadas.values())
print(f"\nEjecución {r.ejecucion}: {total} capturadas, {len(r.peticiones)} conservadas")
print("Descartadas por motivo:")
for motivo, n in sorted(r.descartadas.items(), key=lambda x: -x[1]):
    print(f"   {motivo:<18} {n:>4}")
print("Conservadas por sesión:", dict(Counter(p.sesion for p in r.peticiones)))
print("\nEndpoints conservados:")
for e in sorted({f"{p.metodo} {p.ruta}" + (f"?{p.consulta}" if p.consulta else "") for p in r.peticiones}):
    print(f"   {e}")

texto = archivo.read_text(encoding="utf-8")
canario_a = next(o.canario for o in r.inventario if o.cuenta == "A" and o.tipo == "direccion")
claves = {c.clave for c in alcance.cuentas}
criterios = {
    "Solo quedan peticiones a la API y con JSON": all(
        p.ruta.startswith(tuple(alcance.prefijos_api)) and "json" in p.tipo_contenido for p in r.peticiones),
    "No quedan duplicados exactos": len({(p.sesion, p.metodo, p.ruta, p.consulta, p.cuerpo_peticion)
                                         for p in r.peticiones}) == len(r.peticiones),
    "La evidencia no contiene claves ni tokens": not any(c in texto for c in claves)
        and not any(s.token in texto for s in sesiones.values()),
    "El inventario quedó guardado con su dueño": len(r.inventario) >= 8,
    "El canario de A sigue en la sesión A tras filtrar": any(
        canario_a in p.cuerpo_respuesta for p in r.peticiones if p.sesion == "A"),
    "La evidencia se vuelve a leer sin pérdida": ResultadoExploracion.model_validate_json(texto) == r,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
print(f"\nEvidencia guardada en {archivo}")
