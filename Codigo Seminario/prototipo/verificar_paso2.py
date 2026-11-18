"""Paso 2 del Explorador: prepara las cuentas A y B en Juice Shop y comprueba lo sembrado.

Uso (Juice Shop corriendo en Docker; desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_paso2.py
"""
from pathlib import Path

import requests

from prototipo.juice_shop import preparar
from prototipo.modelos import Alcance

alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
sesiones = preparar(alcance)

for nombre, s in sesiones.items():
    print(f"\nCuenta {nombre}: {s.cuenta.correo}, id de usuario {s.cuenta.id_usuario}")
    for o in s.inventario:
        print(f"   {o.tipo:<13} id {o.id:<4} {o.canario or ''}")

todos = [o for s in sesiones.values() for o in s.inventario]
canarios = [o.canario for o in todos if o.canario]
A, B = sesiones["A"], sesiones["B"]
ids = lambda s, tipo: {o.id for o in s.inventario if o.tipo == tipo}


def lee_su_canario(s) -> bool:
    """El dueño puede leer cada objeto con canario, y el canario aparece en la respuesta."""
    rutas = {"direccion": "/api/Addresss/", "tarjeta": "/api/Cards/"}
    for o in s.inventario:
        if o.canario:
            r = requests.get(f"{alcance.url_base}{rutas[o.tipo]}{o.id}", timeout=10,
                             headers={"Authorization": f"Bearer {s.token}"})
            if r.status_code != 200 or o.canario not in r.text:
                return False
    return True


criterios = {
    "A y B son usuarios distintos": A.cuenta.id_usuario != B.cuenta.id_usuario,
    "Cada cuenta tiene dirección y tarjeta con canario": all(
        {"direccion", "tarjeta"} <= {o.tipo for o in s.inventario if o.canario} for s in sesiones.values()),
    "Los canarios son únicos": len(canarios) == len(set(canarios)),
    "Los objetos de A y B no comparten id": all(not ids(A, t) & ids(B, t) for t in ("canasta", "direccion", "tarjeta")),
    "Cada dueño lee sus objetos y ve su canario": all(lee_su_canario(s) for s in sesiones.values()),
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
