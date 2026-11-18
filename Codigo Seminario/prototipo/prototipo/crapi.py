"""Adaptador de OWASP crAPI 1.1.5: registro, vehículo y reporte de mecánico con datos canario, y navegación.

Sigue la interfaz de adaptadores.py, igual que juice_shop.py. Lo que siembra en cada cuenta (A y B):
  - vehículo: el VIN y el pincode llegan por correo a MailHog al registrarse; su ubicación es el
    desafío BOLA 1 de crAPI (GET /identity/api/v2/vehicle/{uuid}/location);
  - reporte de mecánico: se contacta a un mecánico con el canario en problem_details; el reporte es el
    desafío BOLA 2 (GET /workshop/api/mechanic/mechanic_report?report_id=<id>).
Estas peticiones no pasan por el proxy: preparan el ambiente y no forman parte de la captura.

Valores tomados del código de crAPI 1.1.5 (../crAPI-main), pendientes de confirmar con crAPI corriendo
(probar_crapi.py los imprime):
  - el correo de bienvenida solo llega a MailHog si el dominio del correo es example.com
    (MAILHOG_DOMAIN=example.com en deploy/docker/docker-compose.yml; si no, crAPI intenta enviarlo por
    smtp.example.com y el envío falla sin aviso). Por eso las cuentas de alcance_crapi.json son @example.com;
  - el correo es HTML: "VIN: <font ...>XXXXXXXXXXXXXXXXX</font> ... Pincode: <font ...>1234</font>"
    (identity/.../utils/MailBody.java); el VIN tiene 17 caracteres y el pincode 4 dígitos (GenerateVIN.java);
  - registro: name entre 3 y 100 caracteres sin restricción de caracteres (acepta el canario), password de
    6 a 100, number de hasta 15 y único por usuario (SignUpForm.java, UserRegistrationServiceImpl.java);
  - el dashboard devuelve el id del usuario en "id" (DashboardResponse.java);
  - contactar al mecánico responde {"response_from_mechanic_api": {"id": <id>, "sent": true,
    "report_link": ".../mechanic_report?report_id=<id>"}, "status": 200} (workshop/crapi/mechanic/views.py).
"""
import email
import hashlib
import re
import time
from urllib.parse import parse_qs, urlsplit

import requests

from prototipo.modelos import Alcance, CuentaExplorada, CuentaPrueba, ObjetoSembrado
from prototipo.sesion import SesionPreparada, nuevo_canario

TIEMPO_ESPERA = 10   # segundos por petición
ESPERA_CORREO = 30   # segundos máximos esperando el correo del VIN en MailHog
PUERTO_MAILHOG = 8025

# Endpoint que entrega cada tipo de objeto sembrado (el Analista lo usa con los ids que van en la ruta).
# El reporte lleva su id en la consulta, así que su dueño se busca por PARAMETROS.
ENDPOINTS = {"vehiculo": "/identity/api/v2/vehicle/{id}/location",
             "reporte": "/workshop/api/mechanic/mechanic_report"}

# Nombre con que crAPI envía el id de cada objeto en la consulta o el cuerpo (en minúsculas).
# GET /workshop/api/mechanic/mechanic_report?report_id=5 -> report_id es un reporte.
PARAMETROS = {"report_id": "reporte"}

_VIN = re.compile(r"VIN:\s*([A-Z0-9]{17})")
_PINCODE = re.compile(r"Pincode:\s*(\d{3,6})")


def _url_mailhog(url_base: str) -> str:
    """MailHog atiende en el mismo servidor que crAPI, en el puerto 8025 (docker-compose.yml)."""
    return f"{urlsplit(url_base).scheme}://{urlsplit(url_base).hostname}:{PUERTO_MAILHOG}"


def verificar_disponible(url_base: str) -> None:
    for nombre, url in (("identity", f"{url_base}/identity/health_check"),
                        ("workshop", f"{url_base}/workshop/health_check/"),
                        ("MailHog", f"{_url_mailhog(url_base)}/api/v2/messages?limit=1")):
        try:
            requests.get(url, timeout=TIEMPO_ESPERA).raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"No respondió el servicio {nombre} de crAPI ({url}). ¿Están corriendo los "
                               f"contenedores? (cd ../crAPI-main/deploy/docker && docker compose ps)") from e


def _numero(correo: str) -> str:
    """Teléfono para el registro: crAPI exige uno distinto por usuario. Se deriva del correo para que
    sea el mismo en cada ejecución (solo dígitos, como pide la interfaz)."""
    return "9" + str(int(hashlib.sha256(correo.encode()).hexdigest(), 16))[:9]


def _registrar(url: str, c: CuentaPrueba, nombre: str) -> bool:
    """Registra la cuenta. Devuelve False si ya existía (crAPI responde 403 y se sigue)."""
    r = requests.post(f"{url}/identity/api/auth/signup", timeout=TIEMPO_ESPERA, json={
        "name": nombre, "email": c.correo, "number": _numero(c.correo), "password": c.clave})
    if r.status_code == 200:
        return True
    if r.status_code == 403:  # correo o teléfono ya registrados
        return False
    raise RuntimeError(f"crAPI rechazó el registro de la cuenta {c.nombre} ({c.correo}): {r.status_code} {r.text[:200]}")


def _iniciar_sesion(url: str, c: CuentaPrueba) -> str:
    r = requests.post(f"{url}/identity/api/auth/login", json={"email": c.correo, "password": c.clave},
                      timeout=TIEMPO_ESPERA)
    if r.status_code != 200 or not r.json().get("token"):
        raise RuntimeError(f"La cuenta {c.nombre} ({c.correo}) no pudo iniciar sesión: {r.status_code}")
    return r.json()["token"]


def _leer_correo_vehiculo(url_mailhog: str, correo: str) -> tuple[str, str] | None:
    """Busca en MailHog el correo de bienvenida más reciente de la cuenta y extrae el VIN y el pincode."""
    r = requests.get(f"{url_mailhog}/api/v2/search", params={"kind": "to", "query": correo, "limit": 50},
                     timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    for item in r.json().get("items", []):  # MailHog los entrega del más reciente al más antiguo
        mensaje = email.message_from_string(item.get("Raw", {}).get("Data", ""))
        partes = mensaje.walk() if mensaje.is_multipart() else [mensaje]
        for parte in partes:
            contenido = parte.get_payload(decode=True)  # decodifica quoted-printable o base64
            if not contenido:
                continue
            texto = re.sub(r"<[^>]+>", " ", contenido.decode(parte.get_content_charset() or "utf-8", "replace"))
            vin, pin = _VIN.search(texto), _PINCODE.search(texto)
            if vin and pin:
                return vin.group(1), pin.group(1)
    return None


def _esperar_correo_vehiculo(url: str, cab: dict, c: CuentaPrueba) -> tuple[str, str]:
    url_mailhog = _url_mailhog(url)
    datos = _leer_correo_vehiculo(url_mailhog, c.correo)
    if datos is None:  # p. ej. MailHog se reinició: se pide a crAPI que reenvíe el correo
        requests.post(f"{url}/identity/api/v2/vehicle/resend_email", headers=cab, timeout=TIEMPO_ESPERA)
        limite = time.monotonic() + ESPERA_CORREO
        while datos is None and time.monotonic() < limite:
            time.sleep(2)
            datos = _leer_correo_vehiculo(url_mailhog, c.correo)
    if datos is None:
        aviso = "" if c.correo.lower().endswith("@example.com") else \
            " crAPI solo envía a MailHog los correos @example.com."
        raise RuntimeError(f"No llegó a MailHog el correo con el VIN de la cuenta {c.nombre} ({c.correo}).{aviso}")
    return datos


def _vehiculo(url: str, cab: dict, c: CuentaPrueba) -> dict:
    """Devuelve el vehículo de la cuenta; si no tiene, lo agrega con el VIN y el pincode del correo."""
    r = requests.get(f"{url}/identity/api/v2/vehicle/vehicles", headers=cab, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    if r.json():
        return r.json()[0]  # ya se agregó en una ejecución anterior: se reutiliza
    vin, pincode = _esperar_correo_vehiculo(url, cab, c)
    r = requests.post(f"{url}/identity/api/v2/vehicle/add_vehicle", headers=cab, timeout=TIEMPO_ESPERA,
                      json={"vin": vin, "pincode": pincode})
    if r.status_code != 200:
        raise RuntimeError(f"crAPI no agregó el vehículo de la cuenta {c.nombre}: {r.status_code} {r.text[:200]}")
    r = requests.get(f"{url}/identity/api/v2/vehicle/vehicles", headers=cab, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    return next(v for v in r.json() if v.get("vin") == vin)


def _contactar_mecanico(url: str, cab: dict, vin: str, detalle: str) -> str:
    """Crea un reporte de mecánico y devuelve su report_id.

    El campo mechanic_api es una URL que llama el servidor workshop, no este programa. La interfaz envía
    la del navegador (<url_base>/workshop/...), pero dentro de Docker "localhost" es el propio contenedor;
    si así no conecta, se usa el nombre interno del servicio web en la red de Docker (crapi-web).
    """
    r = requests.get(f"{url}/workshop/api/mechanic/", headers=cab, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    codigo = r.json()["mechanics"][0]["mechanic_code"]
    for base in (url, "http://crapi-web"):
        r = requests.post(f"{url}/workshop/api/merchant/contact_mechanic", headers=cab, timeout=3 * TIEMPO_ESPERA,
                          json={"mechanic_code": codigo, "problem_details": detalle, "vin": vin,
                                "mechanic_api": f"{base}/workshop/api/mechanic/receive_report",
                                "repeat_request_if_failed": False, "number_of_repeats": 1})
        if r.status_code == 200:
            respuesta = r.json()["response_from_mechanic_api"]
            if respuesta.get("id") is not None:
                return str(respuesta["id"])
            return parse_qs(urlsplit(respuesta["report_link"]).query)["report_id"][0]
    raise RuntimeError(f"crAPI no creó el reporte de mecánico: {r.status_code} {r.text[:200]}")


def preparar_cuenta(alcance: Alcance, c: CuentaPrueba) -> SesionPreparada:
    """Registra la cuenta si no existe, inicia sesión y siembra el vehículo y el reporte con datos canario."""
    url = alcance.url_base
    nueva = _registrar(url, c, f"Titular {nuevo_canario(c.nombre)}")
    token = _iniciar_sesion(url, c)
    cab = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{url}/identity/api/v2/user/dashboard", headers=cab, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    usuario = r.json()
    sesion = SesionPreparada(CuentaExplorada(nombre=c.nombre, correo=c.correo, id_usuario=str(usuario["id"])),
                             token, cabeceras_auth=cab)
    inv = sesion.inventario

    # El nombre de la cuenta lleva un canario desde su registro; la ubicación del vehículo lo devuelve en
    # "fullName". Si la cuenta ya existía con otro nombre, el vehículo queda sin canario y el oráculo usa
    # el inventario.
    m = re.search(rf"Canario-{c.nombre}-[0-9A-F]{{8}}", usuario.get("name") or "")
    vehiculo = _vehiculo(url, cab, c)
    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="vehiculo", id=str(vehiculo["uuid"]),
                              canario=m.group(0) if m else None, endpoint=ENDPOINTS["vehiculo"]))

    canario = nuevo_canario(c.nombre)
    reporte = _contactar_mecanico(url, cab, vehiculo["vin"], f"Revisión {canario}")
    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="reporte", id=reporte, canario=canario,
                              endpoint=ENDPOINTS["reporte"]))
    print(f"   crAPI, cuenta {c.nombre}: {'registrada' if nueva else 'ya existía'}, id {usuario['id']}, "
          f"vehículo {vehiculo['uuid']}, reporte {reporte}")
    return sesion


def preparar(alcance: Alcance) -> dict[str, SesionPreparada]:
    verificar_disponible(alcance.url_base)
    return {c.nombre: preparar_cuenta(alcance, c) for c in alcance.cuentas}


# ---------- Navegador (Explorador, paso 3) ----------
def preparar_contexto(ctx, alcance: Alcance) -> None:
    """crAPI no muestra avisos que tapen el formulario: no hace falta ajustar el navegador."""


def iniciar_sesion_navegador(pagina, alcance: Alcance, cuenta: CuentaPrueba) -> None:
    """Inicia sesión en /login (Ant Design: los campos se reconocen por su placeholder) y espera el dashboard.

    La sesión vive en el localStorage del contexto (redux-persist, clave "persist:reducers"), pero se guarda
    con un pequeño retraso. Si el Explorador recarga la página antes, crAPI la trata como no autenticada y
    redirige a /login sin pedir datos (corrida del 18/11). Por eso se espera a que quede guardada con
    isLoggedIn = true. Si no llega al dashboard o la sesión no se guarda, avisa y la exploración sigue.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout  # solo se necesita al navegar
    pagina.goto(f"{alcance.url_base}/login")
    pagina.fill('input[placeholder="Email"]', cuenta.correo)
    pagina.fill('input[placeholder="Password"]', cuenta.clave)
    pagina.click('button[type="submit"]')
    try:
        pagina.wait_for_url("**/dashboard", timeout=15000)
        pagina.wait_for_function(_SESION_GUARDADA, timeout=10000)
    except PlaywrightTimeout:
        print(f"   AVISO: la sesión {cuenta.nombre} no llegó al dashboard o no quedó guardada; "
              f"revisa el inicio de sesión.")
        return
    try:
        pagina.wait_for_load_state("networkidle", timeout=10000)  # deja terminar las llamadas del dashboard
    except PlaywrightTimeout:
        pass  # la página sigue con llamadas en curso; no impide seguir


# Verdadero cuando redux-persist ya guardó la sesión iniciada (el token no sale del navegador)
_SESION_GUARDADA = """() => {
    const guardado = localStorage.getItem("persist:reducers");
    if (!guardado) return false;
    const usuario = JSON.parse(JSON.parse(guardado).userReducer || "{}");
    return usuario.isLoggedIn === true && !!usuario.accessToken;
}"""
