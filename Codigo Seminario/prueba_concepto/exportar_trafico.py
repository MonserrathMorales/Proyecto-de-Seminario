"""Comprobaciones 1 y 2: revisa la captura autenticada y la convierte en casos para el Analista.

Uso (después de prueba_captura_sesiones.py y con mitmdump ya detenido):
    python exportar_trafico.py [captura_sesiones.mitm]
Muestra el resumen por sesión y los criterios de aceptación de la captura, y genera
casos_juice.json con el formato de casos_analista.json y el campo "esperado" vacío,
para etiquetarlo a mano.
"""
import json
import sys
from pathlib import Path

from mitmproxy import http, io

CARPETA = Path(__file__).parent
CAPTURA = Path(sys.argv[1]) if len(sys.argv) > 1 else CARPETA / "captura_sesiones.mitm"
CUENTAS = json.loads((CARPETA / "cuentas_juice.json").read_text(encoding="utf-8"))
MAX_RESPUESTA = 1500  # caracteres; mantiene cada caso dentro del contexto de 4.096 tokens

# ---------- Lectura y filtrado (lista cerrada: solo la API de Juice Shop) ----------
peticiones = []
with CAPTURA.open("rb") as f:
    for flujo in io.FlowReader(f).stream():
        if not isinstance(flujo, http.HTTPFlow) or flujo.response is None or flujo.websocket is not None:
            continue
        pet, res = flujo.request, flujo.response
        if pet.port != 3000 or not pet.path.startswith(("/rest/", "/api/")):
            continue
        if "json" not in res.headers.get("content-type", ""):
            continue
        peticiones.append({
            "sesion": pet.headers.get("X-Sesion", "sin_etiqueta"), "metodo": pet.method, "ruta": pet.path,
            "cuerpo": pet.get_text(strict=False) or "", "autorizacion": "Authorization" in pet.headers,
            "estado": res.status_code, "motivo": res.reason or "", "respuesta": res.get_text(strict=False) or ""})

# ---------- Resumen y criterios de aceptación de la captura ----------
print(f"Peticiones a la API capturadas: {len(peticiones)}")
for sesion in ("A", "B", "anonima"):
    ps = [p for p in peticiones if p["sesion"] == sesion]
    rutas = sorted({f"{p['metodo']} {p['ruta']}" for p in ps})
    print(f"\nSesión {sesion}: {len(ps)} peticiones, {len(rutas)} distintas, "
          f"{sum(p['autorizacion'] for p in ps)} con cabecera Authorization")
    for r in rutas:
        print(f"   {r}")


def aparece(texto: str, sesion: str) -> bool:
    return any(texto in p["respuesta"] for p in peticiones if p["sesion"] == sesion)


def pidio(fragmento: str, sesion: str) -> bool:
    return any(fragmento in p["ruta"] for p in peticiones if p["sesion"] == sesion)


criterios = {
    "A y B enviaron peticiones autenticadas": all(
        any(p["autorizacion"] for p in peticiones if p["sesion"] == s) for s in ("A", "B")),
    "Cada sesión pidió su propia canasta": all(
        pidio(f"/rest/basket/{CUENTAS[s]['canasta_id']}", s) for s in ("A", "B")),
    "El canario de A aparece en la sesión A": aparece(CUENTAS["A"]["canario"], "A"),
    "El canario de B aparece en la sesión B": aparece(CUENTAS["B"]["canario"], "B"),
    "El canario de A no aparece en la sesión B": not aparece(CUENTAS["A"]["canario"], "B"),
    "La sesión anónima quedó registrada": any(p["sesion"] == "anonima" for p in peticiones),
}
print("\nCriterios de aceptación de la captura")
for nombre, ok in criterios.items():
    print(f"   [{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Exportación de casos para etiquetar ----------
casos, vistos = [], set()
for p in peticiones:
    clave = (p["sesion"], p["metodo"], p["ruta"])
    if p["sesion"] not in ("A", "B") or clave in vistos:
        continue
    vistos.add(clave)
    peticion = f"{p['metodo']} {p['ruta']}" + (f"  cuerpo: {p['cuerpo']}" if p["cuerpo"] else "")
    respuesta = f"{p['estado']} {p['motivo']} {p['respuesta']}".strip()
    casos.append({
        "id": f"J{len(casos) + 1:02d}", "descripcion": "", "sesion": p["sesion"], "peticion": peticion,
        "respuesta": respuesta[:MAX_RESPUESTA] + (" …(recortada)" if len(respuesta) > MAX_RESPUESTA else ""),
        "esperado": {"contiene_identificador": None, "valor": None, "ubicacion": None,
                     "visibilidad": None, "cuenta_duena": None}})

salida = CARPETA / "casos_juice.json"
salida.write_text(json.dumps({
    "usuarios": {s: {"id": CUENTAS[s]["id"], "correo": CUENTAS[s]["correo"]} for s in ("A", "B")},
    "casos": casos}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{len(casos)} casos sin etiquetar guardados en {salida.name}")
