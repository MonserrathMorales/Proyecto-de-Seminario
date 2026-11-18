"""Prueba con OWASP crAPI levantado (Parte D.4): adaptador y, con --grafo, el flujo completo.

Parte 1 (siempre): verifica que crAPI y MailHog respondan, prepara las cuentas A y B con crapi.preparar()
    y muestra en la consola cada petición de preparación (método, ruta, código y un extracto de la
    respuesta, con los tokens ocultos). Imprime los valores reales que el adaptador da por supuestos
    (correo del VIN, nombre con canario, campo del id, formato de report_link).
Parte 2 (--grafo): ejecuta explorador -> analista -> validacion -> cerrar con alcance_crapi.json. Por
    defecto en modo solo_reglas (sin LLM); con --modo reglas_llm el Analista consulta al modelo los
    candidatos pendientes (necesita Ollama abierto). Abre el navegador y usa mitmproxy, igual que con Juice Shop.
Necesita crAPI levantado:
    cd ../crAPI-main/deploy/docker && docker compose pull && docker compose -f docker-compose.yml --compatibility up -d
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python probar_crapi.py
    python probar_crapi.py --grafo
    python probar_crapi.py --grafo --modo reglas_llm
"""
import contextlib
import email
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

from prototipo import crapi
from prototipo.filtro import OCULTO, ocultar_secretos
from prototipo.modelos import Alcance

alcance = Alcance.model_validate_json(Path("alcance_crapi.json").read_text(encoding="utf-8"))
MODO = sys.argv[sys.argv.index("--modo") + 1] if "--modo" in sys.argv else "solo_reglas"
if MODO not in ("solo_reglas", "reglas_llm"):
    raise SystemExit(f"Modo desconocido: {MODO}. Usa solo_reglas o reglas_llm.")
vistas: list[dict] = []   # peticiones de preparación, sin secretos


class Espia:
    """Envuelve a requests dentro del adaptador para mostrar qué pidió y qué respondió crAPI."""
    RequestException = requests.RequestException

    def _anotar(self, metodo, url, r):
        ruta = urlsplit(url)
        vistas.append({"metodo": metodo, "ruta": ruta.path + (f"?{ruta.query}" if ruta.query else ""),
                       "estado": r.status_code, "cuerpo": r.text})
        return r

    def get(self, url, **kw):
        return self._anotar("GET", url, requests.get(url, **kw))

    def post(self, url, **kw):
        return self._anotar("POST", url, requests.post(url, **kw))


class Doble(io.StringIO):
    """Escribe en la consola y guarda una copia, para revisar después que no se imprimió ningún token."""
    def write(self, texto):
        sys.__stdout__.write(texto)
        return super().write(texto)


def sin_tokens(texto: str, tokens: list[str]) -> str:
    texto = ocultar_secretos(texto)
    for t in tokens:
        texto = texto.replace(t, OCULTO)
    return texto


# ---------- Parte 1: adaptador ----------
print(f"Parte 1. Preparación de cuentas en {alcance.url_base} (MailHog en {crapi._url_mailhog(alcance.url_base)})\n")
crapi.requests, original = Espia(), crapi.requests
consola = Doble()
try:
    with contextlib.redirect_stdout(consola):
        sesiones = crapi.preparar(alcance)
finally:
    crapi.requests = original
tokens = [s.token for s in sesiones.values()]

print("\n Peticiones de preparación (no pasan por el proxy):")
for v in vistas:
    extracto = re.sub(r"\s+", " ", sin_tokens(v["cuerpo"], tokens))
    if "/api/v2/search" in v["ruta"]:
        extracto = f"{len(json.loads(v['cuerpo']).get('items', []))} correos encontrados"
    print(f"   {v['metodo']:<5}{v['ruta'][:70]:<72}{v['estado']}  {extracto[:110]}")

print("\n Inventario sembrado:")
for o in (o for s in sesiones.values() for o in s.inventario):
    print(f"   {o.cuenta}  {o.tipo:<9}{o.id:<38}{o.canario or '-':<21}{o.endpoint}")

# Valores que el adaptador tomó del código de crAPI: se muestran los reales
print("\n Valores reales (Datos que hay que confirmar):")
cab_a = {"Authorization": f"Bearer {sesiones['A'].token}"}
tablero = requests.get(f"{alcance.url_base}/identity/api/v2/user/dashboard", headers=cab_a, timeout=10).json()
print(f"   Dashboard: campos {sorted(tablero)}; id = {tablero.get('id')}; name = {tablero.get('name')!r}")
print(f"   ¿El nombre aceptó el canario?: {'sí' if re.search(r'Canario-A-[0-9A-F]{8}', tablero.get('name') or '') else 'no'}")
correos = requests.get(f"{crapi._url_mailhog(alcance.url_base)}/api/v2/search",
                       params={"kind": "to", "query": alcance.cuentas[0].correo, "limit": 1}, timeout=10).json()
if correos.get("items"):
    item = correos["items"][0]
    cabeceras_correo = {k: " ".join(v) for k, v in item["Content"]["Headers"].items()}  # MailHog usa listas
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", email.message_from_string(
        item["Raw"]["Data"]).get_payload(decode=True).decode("utf-8", "replace")))
    print(f"   Correo del VIN: asunto {cabeceras_correo.get('Subject')}, codificación "
          f"{cabeceras_correo.get('Content-Transfer-Encoding')}; texto: ...{texto[texto.find('VIN'):][:60]}...")
else:
    print("   Correo del VIN: MailHog no tiene correos de la cuenta A (¿se registró con otra versión?)")
contactos = [v for v in vistas if v["ruta"].endswith("contact_mechanic")]
for v in contactos:
    print(f"   contact_mechanic -> {v['estado']}: {re.sub(chr(10), ' ', v['cuerpo'])[:160]}")
rep_a = next(o for o in sesiones["A"].inventario if o.tipo == "reporte")
r = requests.get(f"{alcance.url_base}/workshop/api/mechanic/mechanic_report", params={"report_id": rep_a.id},
                 headers=cab_a, timeout=10)
print(f"   mechanic_report de A pedido por A -> {r.status_code}; campos {sorted(r.json())}; "
      f"¿trae el canario?: {'sí' if rep_a.canario in r.text else 'no'}")

impreso = consola.getvalue()
criterios = {
    "crAPI, identity, workshop y MailHog responden": True,   # si no, preparar() se habría detenido antes
    "A y B tienen vehículo y reporte en el inventario": all(
        {o.tipo for o in s.inventario} >= {"vehiculo", "reporte"} for s in sesiones.values()),
    "El reporte guarda su canario y crAPI lo devuelve en mechanic_report": rep_a.canario in r.text,
    "Ningún token aparece en lo impreso": all(t not in impreso for t in tokens) and "eyJ" not in impreso,
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")

# ---------- Parte 2: grafo completo ----------
if "--grafo" in sys.argv:
    from prototipo.grafo import SESIONES, construir
    from prototipo.modelos import ResultadoAnalisis, ResultadoExploracion, ResultadoValidacion
    print(f"\nParte 2. Grafo completo con alcance_crapi.json, modo {MODO} (se abre el navegador)...")
    grafo = construir()
    config = {"configurable": {"thread_id": "crapi"}}
    estado = grafo.invoke({"ruta_alcance": "alcance_crapi.json", "modo_analista": MODO}, config)
    for e in estado["registro"]:
        extra = {k: x for k, x in e.items() if k not in ("etapa", "inicio", "duracion_s", "resultado")}
        print(f"   {e['etapa']:<11} {e['resultado']:<6} {e['duracion_s']:>6} s  {extra}")
    if estado.get("error") or "ruta_validacion" not in estado:
        raise SystemExit(f"\n[FALLA] El flujo no llegó a validar: {estado.get('error')}")

    carpeta = Path(estado["ruta_validacion"]).parent
    expl = ResultadoExploracion.model_validate_json((carpeta / "exploracion.json").read_text(encoding="utf-8"))
    a = ResultadoAnalisis.model_validate_json(Path(estado["ruta_analisis"]).read_text(encoding="utf-8"))
    v = ResultadoValidacion.model_validate_json(Path(estado["ruta_validacion"]).read_text(encoding="utf-8"))
    por_id = {h.id: h for h in a.hipotesis}

    print("\n Endpoints observados:")
    for e in a.endpoints:
        print(f"   {e.clave[:75]:<77}{','.join(e.sesiones)}")
    print(f"\n {'Id':<6}{'Tipo':<11}{'Endpoint':<52}{'Objeto':<10}{'Prueba':<9}{'Veredicto':<12}{'Motivo'}")
    for x in v.veredictos:
        h = por_id[x.hipotesis]
        print(f" {x.hipotesis:<6}{x.tipo:<11}{x.endpoint[:51]:<52}{h.objeto or '-':<10}{h.sesion_prueba:<9}"
              f"{x.clase:<12}{x.motivo}" + (f"  [{x.evidencia}]" if x.clase == "confirmado" else ""))
    print(f"\n Resumen: {v.resumen}   Peticiones enviadas: {v.enviadas}   Omitidas: {v.omitidas or 'ninguna'}")
    print(f" Analista: modo {a.modo}, modelo {a.modelo or '-'}, consultas al modelo {a.consultas_llm}, "
          f"{a.duracion_s} s")
    for c in a.candidatos:
        print(f"   candidato {c.sesion} {c.endpoint[:55]:<57}{c.parametro}={c.valor[:20]:<22}"
              f"{c.decidido_por or 'pendiente':<11}{c.cuenta_duena or '-'}  {c.justificacion[:70]}")

    reportes = [x for x in v.veredictos if por_id[x.hipotesis].objeto == "reporte"]
    ubicacion = [p for p in expl.peticiones if p.ruta.endswith("/location")]
    print(f" Ubicación del vehículo (BOLA 1) en la evidencia: "
          f"{len(ubicacion)} peticiones" + ("" if ubicacion else " (esperable: solo se pide al pulsar Refresh Location)"))
    textos = [f.read_text(encoding="utf-8") for f in carpeta.glob("*.json")]
    punto_control = json.dumps(grafo.get_state(config).values, default=str)
    criterios = {
        "El grafo ejecutó explorador, analista, validacion y cerrar":
            [e["etapa"] for e in estado["registro"]] == ["explorador", "analista", "validacion", "cerrar"],
        "El reporte de mecánico de una cuenta, pedido por la otra, queda confirmado (BOLA 2)": any(
            x.tipo == "horizontal" and x.clase == "confirmado" for x in reportes),
        "Las pruebas sin sesión del reporte quedan descartadas": bool(reportes) and all(
            x.clase == "descartado" for x in reportes if x.tipo == "sin_sesion"),
        # crAPI responde al login con "type": "Bearer" (el token va oculto): se busca un token real
        "Ni datos/<ejecucion>/ ni el estado del grafo contienen tokens (Bearer <token> ni eyJ)": not any(
            re.search(r"Bearer\s+[A-Za-z0-9._-]{8,}|eyJ[A-Za-z0-9_-]{8,}", t) for t in textos + [punto_control]),
        "Las sesiones se liberaron de la memoria al cerrar": estado.get("ejecucion") not in SESIONES,
    }
    print()
    for nombre, ok in criterios.items():
        print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
    print(f"\nEvidencia en {carpeta}")
