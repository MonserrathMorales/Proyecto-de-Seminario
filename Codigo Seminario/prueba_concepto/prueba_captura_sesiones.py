"""Comprobación 1: captura autenticada de Juice Shop con las sesiones A, B y anónima.

Antes de ejecutarlo, en otras dos terminales:
    docker run --rm -p 3000:3000 bkimminich/juice-shop
    mitmdump -p 8080 -w captura_sesiones.mitm        (entorno virtual activado)
Uso:
    python prueba_captura_sesiones.py
Genera cuentas_juice.json con las cuentas, sus ids y los datos canario sembrados.
Al terminar, detén mitmdump con Ctrl+C para que cierre el archivo de captura.
"""
import base64
import json
import secrets
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"
PROXY = "http://127.0.0.1:8080"
CLAVE = "Prueba-2026!"
CUENTAS = {"A": "a.canario@prueba.cl", "B": "b.canario@prueba.cl"}
# Pantallas que cargan objetos privados del usuario (canasta, direcciones, pedidos, tarjetas)
PANTALLAS = ["/#/search", "/#/basket", "/#/address/saved", "/#/order-history", "/#/saved-payment-methods"]
SALIDA = Path(__file__).with_name("cuentas_juice.json")


def id_del_token(token: str) -> int:
    """Lee el id del usuario desde el contenido del JWT (sin validar la firma)."""
    cuerpo = token.split(".")[1]
    cuerpo += "=" * (-len(cuerpo) % 4)
    return json.loads(base64.urlsafe_b64decode(cuerpo))["data"]["id"]


def preparar(nombre: str, correo: str) -> dict:
    """Crea la cuenta (si no existe), inicia sesión y siembra sus datos canario. No pasa por el proxy."""
    requests.post(f"{BASE}/api/Users", timeout=10,
                  json={"email": correo, "password": CLAVE, "passwordRepeat": CLAVE})
    r = requests.post(f"{BASE}/rest/user/login", json={"email": correo, "password": CLAVE}, timeout=10)
    r.raise_for_status()
    aut = r.json()["authentication"]
    cabeceras = {"Authorization": f"Bearer {aut['token']}"}

    canario = f"Canario-{nombre}-{secrets.token_hex(3).upper()}"  # prefijo fijo y sufijo aleatorio
    d = requests.post(f"{BASE}/api/Addresss", headers=cabeceras, timeout=10, json={
        "country": "Chile", "fullName": f"Titular {canario}", "mobileNum": 912345678, "zipCode": "2340000",
        "streetAddress": f"Calle {canario}", "city": "Valparaíso", "state": "Valparaíso"})
    d.raise_for_status()
    b = requests.post(f"{BASE}/api/BasketItems", headers=cabeceras, timeout=10,
                      json={"ProductId": 1, "BasketId": str(aut["bid"]), "quantity": 1})
    if b.status_code >= 400:
        print(f"  Aviso: no se pudo agregar un producto a la canasta de {nombre} ({b.status_code})")
    cuenta = {"correo": correo, "id": id_del_token(aut["token"]), "canasta_id": aut["bid"],
              "direccion_id": d.json()["data"]["id"], "canario": canario}
    print(f"  Cuenta {nombre}: {cuenta}")
    return cuenta


def navegar(navegador, sesion: str, correo: str | None) -> None:
    """Recorre las pantallas con una sesión. La cabecera X-Sesion solo etiqueta la captura."""
    contexto = navegador.new_context(extra_http_headers={"X-Sesion": sesion})
    # Evita los avisos de bienvenida y de cookies, que tapan el formulario de inicio de sesión
    contexto.add_cookies([{"name": n, "value": "dismiss", "url": BASE}
                          for n in ("welcomebanner_status", "cookieconsent_status")])
    pagina = contexto.new_page()
    if correo:
        pagina.goto(f"{BASE}/#/login")
        pagina.fill("#email", correo)
        pagina.fill("#password", CLAVE)
        pagina.click("#loginButton")
        try:
            pagina.wait_for_url("**/#/search", timeout=10000)
        except PlaywrightTimeout:
            print(f"  AVISO: la sesión {sesion} no llegó a la página principal; revisa el inicio de sesión.")
    for ruta in PANTALLAS:
        pagina.goto(f"{BASE}{ruta}")
        pagina.wait_for_timeout(3000)  # deja que la pantalla termine sus llamadas a la API
    print(f"  Sesión {sesion}: {len(PANTALLAS)} pantallas recorridas")
    contexto.close()


if __name__ == "__main__":
    print("1. Preparando cuentas y datos canario")
    cuentas = {nombre: preparar(nombre, correo) for nombre, correo in CUENTAS.items()}
    SALIDA.write_text(json.dumps(cuentas, ensure_ascii=False, indent=2), encoding="utf-8")

    print("2. Navegando a través del proxy")
    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=False, proxy={"server": PROXY},
            args=["--proxy-bypass-list=<-loopback>"])  # sin esto, Chromium no envía localhost por el proxy
        navegar(navegador, "A", CUENTAS["A"])
        navegar(navegador, "B", CUENTAS["B"])
        navegar(navegador, "anonima", None)
        navegador.close()
    print(f"Listo. Cuentas guardadas en {SALIDA.name}. Detén mitmdump (Ctrl+C) y ejecuta exportar_trafico.py.")
