"""Paso 5 del Explorador: lo ejecuta como primer nodo del grafo de LangGraph.

Hace dos corridas:
  1. Normal, contra Juice Shop (debe estar corriendo y recién reiniciado).
  2. Con un alcance que apunta a un puerto sin servidor, para comprobar que un error se registra
     y el grafo se cierra ordenadamente en vez de caerse.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_paso5.py
"""
import json
from pathlib import Path

from prototipo.grafo import SESIONES, construir
from prototipo.modelos import Alcance

grafo = construir()
print("Nodos del grafo:", [n for n in grafo.get_graph().nodes if not n.startswith("__")])

# ---------- Corrida 1: normal ----------
print("\n1. Corrida normal (se abre una ventana del navegador)...")
config = {"configurable": {"thread_id": "verificacion-normal"}}
estado = grafo.invoke({"ruta_alcance": "alcance_juice.json"}, config)
for e in estado["registro"]:
    extra = {k: v for k, v in e.items() if k not in ("etapa", "inicio", "duracion_s", "resultado")}
    print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>6} s  {extra}")
carpeta = Path(estado["ruta_exploracion"]).parent if "ruta_exploracion" in estado else None

# ---------- Corrida 2: con error ----------
print("\n2. Corrida con Juice Shop inalcanzable (puerto 3999)...")
alcance = json.loads(Path("alcance_juice.json").read_text(encoding="utf-8"))
alcance["url_base"] = "http://localhost:3999"
Path("alcance_inalcanzable.json").write_text(json.dumps(alcance), encoding="utf-8")
estado_err = grafo.invoke({"ruta_alcance": "alcance_inalcanzable.json"},
                          {"configurable": {"thread_id": "verificacion-error"}})
Path("alcance_inalcanzable.json").unlink()
print(f"   error registrado: {estado_err.get('error', '(ninguno)')[:90]}")

# ---------- Criterios ----------
punto_control = json.dumps(grafo.get_state(config).values, default=str)
claves = [c["clave"] for c in alcance["cuentas"]]
registro = json.loads((carpeta / "registro.json").read_text(encoding="utf-8")) if carpeta else {}
criterios = {
    "El Explorador corrió como nodo y terminó bien": any(
        e["etapa"] == "explorador" and e["resultado"] == "ok" for e in estado["registro"]),
    "El estado apunta a la evidencia guardada": carpeta is not None and Path(estado["ruta_exploracion"]).exists(),
    "El registro de etapas quedó junto a la evidencia": [e["etapa"] for e in registro.get("etapas", [])]
        [:1] + [e["etapa"] for e in registro.get("etapas", [])][-1:] == ["explorador", "cerrar"],
    "El estado del grafo no contiene claves ni tokens": not any(c in punto_control for c in claves)
        and "Bearer" not in punto_control and "eyJ" not in punto_control,
    "Las sesiones se liberaron de la memoria al cerrar": estado.get("ejecucion") not in SESIONES,
    "Un error se registra y el grafo se cierra sin caerse": "Explorador:" in estado_err.get("error", "")
        and estado_err["registro"][-1]["etapa"] == "cerrar",
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
if carpeta:
    print(f"\nEvidencia y registro en {carpeta}")
