"""Adaptador de OWASP Juice Shop: registro, inicio de sesión, siembra de datos canario y navegación.

Junto con crapi.py, es la única parte del sistema que depende de la aplicación evaluada; la interfaz
común está descrita en adaptadores.py.
Las peticiones de preparación no pasan por el proxy: preparan el ambiente y no forman parte de la captura.
"""
import base64
import json

import requests

from prototipo.modelos import Alcance, CuentaExplorada, CuentaPrueba, ObjetoSembrado
# Se reexportan para que el código y los verificadores que los importan desde aquí sigan funcionando
from prototipo.sesion import SesionPreparada, cabeceras, nuevo_canario  # noqa: F401

TIEMPO_ESPERA = 10  # segundos por petición

# Endpoint que entrega cada tipo de objeto sembrado. El Analista lo usa para saber de quién es un id:
# en Juice Shop el 7 puede ser a la vez la dirección de A y la canasta de B.
ENDPOINTS = {"usuario": "/api/Users/{id}", "canasta": "/rest/basket/{id}", "direccion": "/api/Addresss/{id}",
             "tarjeta": "/api/Cards/{id}", "item_canasta": "/api/BasketItems/{id}"}

# Nombre con que Juice Shop envía el id de cada tipo de objeto en la consulta o el cuerpo (en minúsculas).
# Ejemplo: {"ProductId": 2, "BasketId": "6"} -> BasketId es una canasta; ProductId es catálogo y no figura aquí.
PARAMETROS = {"basketid": "canasta", "bid": "canasta", "userid": "usuario", "addressid": "direccion",
              "paymentid": "tarjeta", "cardid": "tarjeta", "basketitemid": "item_canasta"}


def verificar_disponible(url_base: str) -> None:
    try:
        requests.get(f"{url_base}/rest/admin/application-version", timeout=TIEMPO_ESPERA).raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"No se pudo contactar a {url_base}. ¿Está corriendo el contenedor de Juice Shop?") from e


def _id_desde_token(token: str) -> str:
    """Lee el id del usuario desde el contenido del JWT (no valida la firma; no hace falta aquí)."""
    cuerpo = token.split(".")[1]
    cuerpo += "=" * (-len(cuerpo) % 4)
    return str(json.loads(base64.urlsafe_b64decode(cuerpo))["data"]["id"])


def _iniciar_sesion(url: str, c: CuentaPrueba) -> dict:
    r = requests.post(f"{url}/rest/user/login", json={"email": c.correo, "password": c.clave}, timeout=TIEMPO_ESPERA)
    if r.status_code != 200:
        raise RuntimeError(f"La cuenta {c.nombre} ({c.correo}) no pudo iniciar sesión: {r.status_code}")
    return r.json()["authentication"]


def preparar_cuenta(alcance: Alcance, c: CuentaPrueba) -> SesionPreparada:
    """Registra la cuenta si no existe, inicia sesión y siembra objetos con datos canario."""
    url = alcance.url_base
    requests.post(f"{url}/api/Users", timeout=TIEMPO_ESPERA,  # si ya existe, Juice Shop lo rechaza y se sigue
                  json={"email": c.correo, "password": c.clave, "passwordRepeat": c.clave})
    aut = _iniciar_sesion(url, c)
    token, id_usuario = aut["token"], _id_desde_token(aut["token"])
    cab = {"Authorization": f"Bearer {token}"}
    # Juice Shop recibe el mismo token en la cabecera Authorization y en la cookie "token", igual que
    # lo envía el navegador después de iniciar sesión. Así se repiten las peticiones en la validación.
    sesion = SesionPreparada(CuentaExplorada(nombre=c.nombre, correo=c.correo, id_usuario=id_usuario), token,
                             cabeceras_auth={"Authorization": f"Bearer {token}", "Cookie": f"token={token}"})
    inv = sesion.inventario

    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="usuario", id=id_usuario))
    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="canasta", id=str(aut["bid"])))

    canario = nuevo_canario(c.nombre)
    r = requests.post(f"{url}/api/Addresss", headers=cab, timeout=TIEMPO_ESPERA, json={
        "country": "Chile", "fullName": f"Titular {canario}", "mobileNum": 912345678, "zipCode": "2340000",
        "streetAddress": f"Calle {canario}", "city": "Valparaíso", "state": "Valparaíso"})
    r.raise_for_status()
    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="direccion", id=str(r.json()["data"]["id"]), canario=canario))

    canario = nuevo_canario(c.nombre)
    r = requests.post(f"{url}/api/Cards", headers=cab, timeout=TIEMPO_ESPERA, json={
        "fullName": f"Titular {canario}", "cardNum": 4716190207394368, "expMonth": 12, "expYear": 2090})
    r.raise_for_status()
    inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="tarjeta", id=str(r.json()["data"]["id"]), canario=canario))

    # Un producto en la canasta, para que su contenido no esté vacío al explorarla
    r = requests.post(f"{url}/api/BasketItems", headers=cab, timeout=TIEMPO_ESPERA,
                      json={"ProductId": 1, "BasketId": str(aut["bid"]), "quantity": 1})
    if r.status_code < 400:
        inv.append(ObjetoSembrado(cuenta=c.nombre, tipo="item_canasta", id=str(r.json()["data"]["id"])))
    for o in inv:
        o.endpoint = ENDPOINTS.get(o.tipo)
    return sesion


def preparar(alcance: Alcance) -> dict[str, SesionPreparada]:
    verificar_disponible(alcance.url_base)
    return {c.nombre: preparar_cuenta(alcance, c) for c in alcance.cuentas}


# ---------- Navegador (Explorador, paso 3) ----------
def preparar_contexto(ctx, alcance: Alcance) -> None:
    """Cierra de antemano el aviso de bienvenida y el de cookies, que tapan el formulario de inicio de sesión."""
    ctx.add_cookies([{"name": n, "value": "dismiss", "url": alcance.url_base}
                     for n in ("welcomebanner_status", "cookieconsent_status")])


def iniciar_sesion_navegador(pagina, alcance: Alcance, cuenta: CuentaPrueba) -> None:
    """Inicia sesión en la interfaz. Si no llega a la página principal, avisa y la exploración sigue."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout  # solo se necesita al navegar
    pagina.goto(f"{alcance.url_base}/#/login")
    pagina.fill("#email", cuenta.correo)
    pagina.fill("#password", cuenta.clave)
    pagina.click("#loginButton")
    try:
        pagina.wait_for_url("**/#/search", timeout=10000)
    except PlaywrightTimeout:
        print(f"   AVISO: la sesión {cuenta.nombre} no llegó a la página principal; revisa el inicio de sesión.")
