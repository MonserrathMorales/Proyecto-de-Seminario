"""Demostración del Explorador: una corrida completa dentro del grafo, con un resumen legible.

Uso (Juice Shop recién reiniciado; desde la carpeta prototipo, con el entorno virtual activado):
    python demo_explorador.py
"""
import json
from pathlib import Path

from prototipo.grafo import construir
from prototipo.modelos import ResultadoExploracion


def titulo(texto):
    print(f"\n{'=' * 64}\n {texto}\n{'=' * 64}")


alcance = json.loads(Path("alcance_juice.json").read_text(encoding="utf-8"))
titulo("1. ALCANCE AUTORIZADO (lista cerrada, RF01)")
print(f" Aplicación : {alcance['aplicacion']} ({alcance['url_base']})")
print(f" Cuentas    : {', '.join(c['nombre'] + ' = ' + c['correo'] for c in alcance['cuentas'])}")
print(f" Pantallas  : {len(alcance['pantallas'])}    Prefijos de la API: {alcance['prefijos_api']}")

titulo("2. EJECUCIÓN (se abre el navegador: A, luego B, luego sin sesión)")
estado = construir().invoke({"ruta_alcance": "alcance_juice.json"}, {"configurable": {"thread_id": "demo"}})
if estado.get("error"):
    raise SystemExit(f"\n La ejecución falló: {estado['error']}")
r = ResultadoExploracion.model_validate_json(Path(estado["ruta_exploracion"]).read_text(encoding="utf-8"))
duracion = next(e["duracion_s"] for e in estado["registro"] if e["etapa"] == "explorador")

titulo("3. INVENTARIO: objetos sembrados y su dueño")
for o in r.inventario:
    print(f" Cuenta {o.cuenta}  {o.tipo:<13} id {o.id:<4} {o.canario or ''}")

titulo("4. FILTRO DEL TRÁFICO (RF10)")
total = len(r.peticiones) + sum(r.descartadas.values())
print(f" Capturadas: {total}    Conservadas para el Analista: {len(r.peticiones)}"
      f"    Descartadas: {round(100 * (1 - len(r.peticiones) / total))}%")
for motivo, n in sorted(r.descartadas.items(), key=lambda x: -x[1]):
    print(f"   - {motivo:<18} {n}")

titulo("5. CANDIDATOS PARA EL AGENTE DE VALIDACIÓN Y REMEDIACIÓN: objetos privados pedidos por id")
ids = {(o.cuenta, o.id): o for o in r.inventario if o.tipo in ("canasta", "direccion")}
for p in r.peticiones:
    partes = p.ruta.rstrip("/").split("/")
    o = ids.get((p.sesion, partes[-1])) if p.sesion in ("A", "B") else None
    if o and ((o.tipo == "canasta" and "/basket/" in p.ruta) or (o.tipo == "direccion" and "Addresss" in p.ruta)):
        print(f" Sesión {p.sesion}: {p.metodo} {p.ruta:<20} -> {o.tipo} de {o.cuenta}"
              + ("  (con canario)" if o.canario else ""))

titulo("6. CONTROL DEL DATO CANARIO")
can_a = next(o.canario for o in r.inventario if o.cuenta == "A" and o.tipo == "direccion")
en = lambda s: any(can_a in p.cuerpo_respuesta for p in r.peticiones if p.sesion == s)
print(f" Canario de A: {can_a}")
print(f"   ¿Aparece en el tráfico de A?  {'Sí' if en('A') else 'No'}   (debe ser Sí: el dueño ve su dato)")
print(f"   ¿Aparece en el tráfico de B?  {'Sí' if en('B') else 'No'}   (debe ser No en la navegación normal)")

titulo("7. EVIDENCIA GUARDADA")
carpeta = Path(estado["ruta_exploracion"]).parent
print(f" {carpeta}\\exploracion.json   (tráfico filtrado + inventario, sin claves ni tokens)")
print(f" {carpeta}\\registro.json      (etapas del grafo y su duración)")
print(f" Duración del Explorador: {duracion} s\n")
