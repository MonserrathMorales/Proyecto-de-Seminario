"""Paso 1 del Explorador: verifica que el alcance se lee bien y que los formatos de datos funcionan.

Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_paso1.py
"""
from datetime import datetime
from pathlib import Path

from prototipo.modelos import (Alcance, CuentaExplorada, ObjetoSembrado, PeticionCapturada,
                               ResultadoExploracion)

alcance = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
print(f"[OK] Alcance leído: {alcance.aplicacion}, {len(alcance.cuentas)} cuentas, "
      f"{len(alcance.pantallas)} pantallas, prefijos {alcance.prefijos_api}")

ejemplo = ResultadoExploracion(
    ejecucion="prueba", fecha=datetime.now(), aplicacion=alcance.aplicacion,
    cuentas=[CuentaExplorada(nombre="A", correo="a.canario@prueba.cl", id_usuario="25")],
    inventario=[ObjetoSembrado(cuenta="A", tipo="direccion", id="7", canario="Canario-A-8B06B4")],
    peticiones=[PeticionCapturada(id="A-0001", sesion="A", metodo="GET", ruta="/api/Addresss/7", estado=200,
                                  tipo_contenido="application/json", autenticada=True,
                                  cuerpo_respuesta='{"data":{"UserId":25,"id":7}}')])
copia = ResultadoExploracion.model_validate_json(ejemplo.model_dump_json())
print(f"[OK] Formato de salida: se guarda y se vuelve a leer sin pérdida ({copia == ejemplo})")
