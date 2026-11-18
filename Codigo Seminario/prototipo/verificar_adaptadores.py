"""Adaptadores: comprueba que el prototipo elige Juice Shop o crAPI según el alcance, sin servicios.

No necesita Juice Shop, crAPI, Ollama ni el navegador. Las aplicaciones se simulan dentro de este
archivo; no se modifica datos/. Comprueba:
  - que cada alcance elige su adaptador y que ambos cumplen la interfaz de adaptadores.py;
  - que las cabeceras de autenticación salen del adaptador (Juice Shop: Bearer y cookie; sin sesión: nada);
  - que las pantallas de crAPI con id en la consulta se completan con el inventario;
  - que no queda código propio de una aplicación fuera de los adaptadores;
  - que el adaptador de crAPI siembra vehículo y reporte, y que el Analista asigna el dueño del reporte
    (id en la consulta) con el inventario, sin el modelo.
Uso (desde la carpeta prototipo, con el entorno virtual activado):
    python verificar_adaptadores.py
"""
import ast
import base64
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path


def _simular_si_falta(nombre: str, **atributos) -> None:
    """Si mitmproxy o Playwright no están instalados, los reemplaza por un módulo vacío (captura.py los importa)."""
    try:
        instalado = importlib.util.find_spec(nombre) is not None
    except (ImportError, ValueError):
        instalado = False
    if not instalado:
        modulo = types.ModuleType(nombre)
        modulo.__dict__.update(atributos)
        sys.modules[nombre] = modulo


_simular_si_falta("mitmproxy", http=types.ModuleType("mitmproxy.http"), io=types.ModuleType("mitmproxy.io"))
_simular_si_falta("playwright")
_simular_si_falta("playwright.sync_api", TimeoutError=TimeoutError, sync_playwright=None)

import requests  # noqa: E402

from prototipo import crapi, juice_shop  # noqa: E402
from prototipo.adaptadores import INTERFAZ, adaptador_de  # noqa: E402
from prototipo.analista import analizar  # noqa: E402
from prototipo.captura import pantallas_de  # noqa: E402
from prototipo.cruce import enviar, ruta_relativa  # noqa: E402
from prototipo.filtro import filtrar  # noqa: E402
from prototipo.juice_shop import SesionPreparada  # noqa: E402  (importación que usan los verificadores)
from prototipo.modelos import (Alcance, CuentaExplorada, ObjetoSembrado, ParCruzado, PeticionCapturada,  # noqa: E402
                               ResultadoAnalisis, ResultadoExploracion, Respuesta)
from prototipo.oraculo import juzgar  # noqa: E402
from prototipo.sesion import cabeceras  # noqa: E402

juice = Alcance.model_validate_json(Path("alcance_juice.json").read_text(encoding="utf-8"))
alcance_crapi = Alcance.model_validate_json(Path("alcance_crapi.json").read_text(encoding="utf-8"))
cuenta_a = CuentaExplorada(nombre="A", correo="a@prueba.cl", id_usuario="1")


class RespuestaFalsa:
    def __init__(self, estado: int, dato):
        self.status_code = estado
        self.text = dato if isinstance(dato, str) else json.dumps(dato)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Eco:
    """Aplicación que solo anota las cabeceras que recibe."""
    def __init__(self):
        self.cabeceras = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.cabeceras.append(dict(headers or {}))
        return RespuestaFalsa(200, {"ok": True})


# ---------- 1 y 2. Alcances y adaptadores ----------
interfaz = {n: [x for x in INTERFAZ if not hasattr(adaptador_de(n), x)] for n in ("juice_shop", "crapi")}
print("Interfaz que falta en cada adaptador:", interfaz)

# ---------- 3 y 4. Cabeceras ----------
sin_auth = cabeceras(SesionPreparada(cuenta=cuenta_a, token="T-SIMULADO"))
copia = SesionPreparada(cuenta=cuenta_a, token="T", cabeceras_auth={"Authorization": "Bearer T"})
cabeceras(copia)["X"] = "cambiada"   # la copia no debe alterar la sesión


class JuiceFalso:
    """Juice Shop simulado: lo justo para que juice_shop.preparar_cuenta siembre sus objetos."""
    RequestException = requests.RequestException
    jwt = "e30." + base64.urlsafe_b64encode(json.dumps({"data": {"id": 25}}).encode()).decode().rstrip("=") + ".firma"

    def post(self, url, json=None, headers=None, timeout=None):
        ruta = url.split("3000", 1)[1]
        if ruta == "/rest/user/login":
            return RespuestaFalsa(200, {"authentication": {"token": self.jwt, "bid": 6}})
        return RespuestaFalsa(201, {"data": {"id": {"/api/Addresss": 7, "/api/Cards": 8}.get(ruta, 9)}})


juice_shop.requests, original = JuiceFalso(), juice_shop.requests
try:
    sesion_juice = juice_shop.preparar_cuenta(juice, juice.cuentas[0])
finally:
    juice_shop.requests = original
eco = Eco()
enviar(f"{juice.url_base}/rest/basket/6", sesion_juice, [sesion_juice.token], eco)
enviar(f"{juice.url_base}/rest/basket/6", None, [sesion_juice.token], eco)
print(f"Cabeceras de Juice Shop: {sorted(eco.cabeceras[0])}; sin sesión: {eco.cabeceras[1]}")

# ---------- 5. Pantallas de crAPI con id en la consulta ----------
con_reporte = SesionPreparada(cuenta=cuenta_a, token="T", inventario=[
    ObjetoSembrado(cuenta="A", tipo="vehiculo", id="0b1c", endpoint=crapi.ENDPOINTS["vehiculo"]),
    ObjetoSembrado(cuenta="A", tipo="reporte", id="5", endpoint=crapi.ENDPOINTS["reporte"])])
sin_reporte = SesionPreparada(cuenta=cuenta_a, token="T", inventario=con_reporte.inventario[:1])
pant_con, pant_sin = pantallas_de(alcance_crapi, con_reporte), pantallas_de(alcance_crapi, sin_reporte)
print(f"Pantallas de crAPI con reporte: {pant_con}")
reporte_capturado = PeticionCapturada(
    id="A-0001", sesion="A", host="localhost:8888", metodo="GET", ruta="/workshop/api/mechanic/mechanic_report",
    consulta="report_id=5", estado=200, tipo_contenido="application/json",
    cuerpo_respuesta='{"id": 5, "problem_details": "Revisión Canario-A-0123ABCD"}', autenticada=True)
conservadas, _ = filtrar([reporte_capturado], alcance_crapi)

# ---------- 6. Nada propio de una aplicación fuera de los adaptadores ----------
MARCAS = ("#loginButton", "welcomebanner", "/rest/", "/identity/")


def textos_de_codigo(archivo: Path) -> list[str]:
    """Textos del código, sin docstrings ni comentarios: allí las rutas son solo ejemplos."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


acoplados = {f.name: sorted({m for t in textos_de_codigo(f) for m in MARCAS if m in t})
             for f in sorted(Path("prototipo").glob("*.py")) if f.name not in ("juice_shop.py", "crapi.py")}
acoplados = {k: v for k, v in acoplados.items() if v}
en_comentarios = sorted(f.name for f in Path("prototipo").glob("*.py") if f.name not in ("juice_shop.py", "crapi.py")
                        and any(m in f.read_text(encoding="utf-8") for m in MARCAS))
print(f"Marcas en el código fuera de los adaptadores: {acoplados or 'ninguna'}")
print(f"   (solo como ejemplo en docstrings o comentarios: {', '.join(en_comentarios) or 'ninguno'})")


# ---------- 7. crAPI simulado: siembra completa y correo de MailHog ----------
class CrapiFalso:
    """crAPI 1.1.5 simulado con las respuestas que da su código fuente (ver crapi.py)."""
    RequestException = requests.RequestException
    TOKEN = "eyJhbGciOiJSUzI1NiJ9.SIMULADO.FIRMA"

    def __init__(self):
        self.nombres, self.vehiculos, self.reportes, self.mecanico_api = {}, {}, {}, []
        self.vin = {"a.canario@example.com": "4KCMS34PGXV891023", "b.canario@example.com": "7NWEV19RHXC302411"}

    def _correo(self, token):
        return token.split("|")[1] if token and "|" in token else None

    def get(self, url, headers=None, params=None, timeout=None):
        correo = self._correo((headers or {}).get("Authorization", "").removeprefix("Bearer "))
        if url.endswith(("/health_check", "/health_check/", "messages?limit=1")):
            return RespuestaFalsa(200, {"status": "UP"})
        if url.endswith("/api/v2/search"):  # MailHog: el correo de bienvenida, en quoted-printable
            html = ("<html><body>Hi Titular,<p>Your vehicle information is <b>VIN: </font><font face='calibri' "
                    f"font color='#0000ff'>{self.vin[params['query']]}</font></b> and <b>Pincode: <font "
                    "face='calibri' font color='#0000ff'>4821</font></b></p></body></html>")
            raw = MIMEText(html, "html", "utf-8")
            raw.replace_header("Content-Transfer-Encoding", "quoted-printable")
            raw.set_payload(__import__("quopri").encodestring(html.encode()).decode())
            return RespuestaFalsa(200, {"items": [{"Raw": {"Data": raw.as_string()}}]})
        if url.endswith("/user/dashboard"):
            return RespuestaFalsa(200, {"id": 11 if correo.startswith("a.") else 12, "name": self.nombres[correo], "email": correo})
        if url.endswith("/vehicle/vehicles"):
            return RespuestaFalsa(200, [self.vehiculos[correo]] if correo in self.vehiculos else [])
        if url.endswith("/workshop/api/mechanic/"):
            return RespuestaFalsa(200, {"mechanics": [{"id": 1, "mechanic_code": "TRAC_JHN"}]})
        return RespuestaFalsa(404, {})

    def post(self, url, json=None, headers=None, timeout=None):
        correo = self._correo((headers or {}).get("Authorization", "").removeprefix("Bearer "))
        if url.endswith("/auth/signup"):
            self.nombres[json["email"]] = json["name"]
            return RespuestaFalsa(200, {"message": "User registered successfully!", "status": 200})
        if url.endswith("/auth/login"):
            return RespuestaFalsa(200, {"token": f"{self.TOKEN}|{json['email']}", "type": "Bearer"})
        if url.endswith("/add_vehicle"):
            if json != {"vin": self.vin[correo], "pincode": "4821"}:
                return RespuestaFalsa(403, {"message": "Invalid VIN or pincode"})
            self.vehiculos[correo] = {"uuid": f"0b1c2d3e-0000-4000-8000-00000000000{len(self.vehiculos)}",
                                      "vin": json["vin"]}
            return RespuestaFalsa(200, {"message": "Vehicle Details Added Successfully!", "status": 200})
        if url.endswith("/contact_mechanic"):
            self.mecanico_api.append(json["mechanic_api"])
            if json["mechanic_api"].startswith("http://localhost"):  # dentro de Docker, localhost no es crAPI
                return RespuestaFalsa(400, {"message": "Could not connect to mechanic api."})
            ident = len(self.reportes) + 5
            self.reportes[ident] = json["problem_details"]
            return RespuestaFalsa(200, {"response_from_mechanic_api": {
                "id": ident, "sent": True,
                "report_link": f"http://crapi-web/workshop/api/mechanic/mechanic_report?report_id={ident}"},
                "status": 200})
        return RespuestaFalsa(404, {})


falso = CrapiFalso()
crapi.requests, original = falso, crapi.requests
salida = io.StringIO()
try:
    with contextlib.redirect_stdout(salida):
        sesiones_crapi = crapi.preparar(alcance_crapi)
finally:
    crapi.requests = original
print(salida.getvalue().rstrip())
inventario_crapi = [o for s in sesiones_crapi.values() for o in s.inventario]
for o in inventario_crapi:
    print(f"   inventario: {o.cuenta} {o.tipo:<9}{o.id:<38}{o.canario or '-':<21}{o.endpoint}")

# ---------- 8. Analista y oráculo con evidencia de crAPI simulada ----------
peticiones = []
for nombre, s in sesiones_crapi.items():
    rep = next(o for o in s.inventario if o.tipo == "reporte")
    peticiones.append(reporte_capturado.model_copy(update={
        "id": f"{nombre}-0001", "sesion": nombre, "consulta": f"report_id={rep.id}",
        "cuerpo_respuesta": json.dumps({"id": int(rep.id), "problem_details": falso.reportes[int(rep.id)]})}))
evidencia = ResultadoExploracion(ejecucion="crapi_simulada", fecha=datetime.now(), aplicacion="OWASP crAPI",
                                 adaptador="crapi", cuentas=[s.cuenta for s in sesiones_crapi.values()],
                                 inventario=inventario_crapi, peticiones=peticiones)
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "exploracion.json").write_text(evidencia.model_dump_json(), encoding="utf-8")
    a: ResultadoAnalisis = analizar(Path(tmp) / "exploracion.json", "solo_reglas")
cand_a = next(c for c in a.candidatos if c.sesion == "A")
h_cruce = next(h for h in a.hipotesis if h.tipo == "horizontal" and h.sesion_origen == "A")
print(f"Analista con crAPI: candidato {cand_a.parametro}={cand_a.valor} -> {cand_a.decidido_por}, dueña "
      f"{cand_a.cuenta_duena}, objeto {cand_a.objeto}; hipótesis {h_cruce.id}: {h_cruce.sesion_prueba} pide el "
      f"reporte de {h_cruce.cuenta_duena}, verificación {h_cruce.verificacion} {h_cruce.canario}")
base = Respuesta(estado=200, cuerpo=peticiones[0].cuerpo_respuesta)
fuga = juzgar(ParCruzado(hipotesis=h_cruce.id, sesion_base="A", sesion_prueba="B", base=base, cruce=base), h_cruce)
negado = juzgar(ParCruzado(hipotesis=h_cruce.id, sesion_base="A", sesion_prueba="B", base=base,
                           cruce=Respuesta(estado=403, cuerpo='{"message": "forbidden"}')), h_cruce)

criterios = {
    "alcance_juice.json elige juice_shop y alcance_crapi.json elige crapi":
        juice.adaptador == "juice_shop" and alcance_crapi.adaptador == "crapi",
    "adaptador_de() entrega toda la interfaz para ambos adaptadores": interfaz == {"juice_shop": [], "crapi": []},
    "Una sesión sin cabeceras propias envía solo el Bearer, y sin sesión no envía nada":
        sin_auth == {"Authorization": "Bearer T-SIMULADO"} and cabeceras(None) == {}
        and copia.cabeceras_auth == {"Authorization": "Bearer T"},
    "La sesión de Juice Shop sigue enviando el Bearer y la cookie token, y la anónima nada":
        eco.cabeceras[0] == {"Authorization": f"Bearer {JuiceFalso.jwt}", "Cookie": f"token={JuiceFalso.jwt}"}
        and eco.cabeceras[1] == {},
    "pantallas_de() completa /service-report?id=<id> y lo omite si no hay reporte":
        "/service-report?id=5" in pant_con and not any("service-report" in p for p in pant_sin)
        and len(pant_con) == len(alcance_crapi.pantallas) and len(pant_sin) == len(alcance_crapi.pantallas) - 1,
    "El filtro y ruta_relativa() conservan la consulta del reporte":
        len(conservadas) == 1 and ruta_relativa(conservadas[0]) == "/workshop/api/mechanic/mechanic_report?report_id=5",
    "Fuera de los adaptadores no hay rutas, selectores ni cookies de una aplicación": not acoplados,
    "crAPI: A y B quedan con vehículo (VIN leído de MailHog) y reporte con canario":
        sorted((o.cuenta, o.tipo) for o in inventario_crapi) == [("A", "reporte"), ("A", "vehiculo"),
                                                                 ("B", "reporte"), ("B", "vehiculo")]
        and all(o.canario for o in inventario_crapi) and len(falso.vehiculos) == 2,
    "crAPI: si el mecánico no conecta por localhost, se usa la red interna de Docker":
        falso.mecanico_api[:2] == ["http://localhost:8888/workshop/api/mechanic/receive_report",
                                   "http://crapi-web/workshop/api/mechanic/receive_report"],
    "crAPI: la sesión envía solo el Bearer y ningún token aparece en lo impreso":
        all(cabeceras(s) == {"Authorization": f"Bearer {s.token}"} for s in sesiones_crapi.values())
        and CrapiFalso.TOKEN not in salida.getvalue() and "eyJ" not in salida.getvalue(),
    "Analista: el report_id de la consulta se asigna a su dueña con el inventario, sin modelo":
        cand_a.decidido_por == "inventario" and cand_a.cuenta_duena == "A" and cand_a.objeto == "reporte"
        and a.consultas_llm == 0,
    "Oráculo: B leyendo el reporte de A se confirma por canario; con 403 se descarta":
        h_cruce.verificacion == "canario" and fuga.clase == "confirmado" and fuga.motivo == "canario_del_dueno"
        and negado.clase == "descartado",
}
print()
for nombre, ok in criterios.items():
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}")
