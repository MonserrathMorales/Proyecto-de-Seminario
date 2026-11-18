"""Paso 3 del Explorador: prepara las cuentas, navega y revisa el tráfico capturado.

Uso (Juice Shop corriendo en Docker; desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_paso3.py
No hace falta iniciar mitmdump a mano: el Explorador lo arranca y lo detiene solo.
"""
from collections import Counter
from pathlib import Path

from prototipo.captura import capturar
from prototipo.juice_shop import preparar
from prototipo.modelos import Alcance

alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
print("1. Preparando cuentas"); sesiones = preparar(alcance)
print("2. Navegando y capturando (se abre una ventana del navegador)")
peticiones = capturar(alcance, sesiones)

print(f"\nPeticiones capturadas: {len(peticiones)}")
for s in ("A", "B", "anonima"):
    ps = [p for p in peticiones if p.sesion == s]
    api = [p for p in ps if p.ruta.startswith(tuple(alcance.prefijos_api))]
    print(f"   Sesión {s:<8}: {len(ps):>3} peticiones, {len(api):>3} a la API, "
          f"{sum(p.autenticada for p in ps):>3} autenticadas")
tipos = Counter(p.tipo_contenido.split(";")[0] for p in peticiones)
print("   Tipos de contenido:", dict(tipos.most_common(5)))


def canario(nombre):
    return next(o.canario for o in sesiones[nombre].inventario if o.tipo == "direccion")


def aparece(texto, sesion):
    return any(texto in p.cuerpo_respuesta for p in peticiones if p.sesion == sesion)


criterios = {
    "A y B generaron peticiones autenticadas": all(
        any(p.autenticada for p in peticiones if p.sesion == s) for s in ("A", "B")),
    "Se capturaron peticiones a la API": any(
        p.ruta.startswith(tuple(alcance.prefijos_api)) for p in peticiones),
    "Ruta y consulta quedaron separadas": any(p.consulta for p in peticiones),
    "El canario de A aparece en la sesión A": aparece(canario("A"), "A"),
    "El canario de A no aparece en la sesión B": not aparece(canario("A"), "B"),
    "La sesión anónima quedó registrada": any(p.sesion == "anonima" for p in peticiones),
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
