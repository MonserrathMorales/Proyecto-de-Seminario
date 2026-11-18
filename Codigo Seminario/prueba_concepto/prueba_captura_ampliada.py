"""Comprobación 1 ampliada: captura de Juice Shop con peticiones que referencian objetos por id.

Repite la navegación de prueba_captura_sesiones.py (A, B y anónima) y agrega, para A y B,
peticiones a la API como las que hace la interfaz al abrir el detalle de un objeto:
identificadores en la ruta, en la consulta y en el cuerpo, de objetos privados y públicos.

Requiere prueba_captura_sesiones.py en la misma carpeta. Antes de ejecutarlo:
    docker run --rm -p 3000:3000 bkimminich/juice-shop          (reinícialo para partir de cero)
    mitmdump -p 8080 -w captura_ampliada.mitm                    (entorno virtual activado)
Uso:
    python prueba_captura_ampliada.py
Después, detén mitmdump con Ctrl+C y ejecuta:
    python exportar_trafico.py captura_ampliada.mitm
"""
import json

import requests
from playwright.sync_api import sync_playwright

from prueba_captura_sesiones import BASE, CLAVE, CUENTAS, PROXY, SALIDA, navegar, preparar


def iniciar_sesion(correo: str) -> str:
    """Devuelve un token de sesión. No pasa por el proxy, para no ensuciar la captura."""
    r = requests.post(f"{BASE}/rest/user/login", json={"email": correo, "password": CLAVE}, timeout=10)
    r.raise_for_status()
    return r.json()["authentication"]["token"]


def sembrar_tarjeta(nombre: str, token: str) -> int | None:
    """Crea una tarjeta de pago en la cuenta, para tener otro objeto privado que pedir por id."""
    r = requests.post(f"{BASE}/api/Cards", headers={"Authorization": f"Bearer {token}"}, timeout=10,
                      json={"fullName": f"Titular {nombre}", "cardNum": 4716190207394368,
                            "expMonth": 12, "expYear": 2090})
    if r.status_code >= 400:
        print(f"  Aviso: no se pudo crear la tarjeta de {nombre} ({r.status_code})")
        return None
    return r.json()["data"]["id"]


def llamar_api(nombre: str, cuenta: dict, token: str) -> None:
    """Hace las peticiones a través del proxy, con el token y la etiqueta de la sesión."""
    s = requests.Session()
    s.trust_env = False  # obliga a usar el proxy aunque Windows excluya localhost
    s.proxies = {"http": PROXY}
    s.headers.update({"Authorization": f"Bearer {token}", "X-Sesion": nombre})

    def pedir(metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
        r = s.request(metodo, f"{BASE}{ruta}", json=cuerpo, timeout=10)
        print(f"    {r.status_code}  {metodo} {ruta}")
        try:
            return r.json()
        except ValueError:
            return {}

    print(f"  Sesión {nombre}: peticiones a la API")
    # Identificador en la ruta, objetos privados de la propia cuenta
    pedir("GET", f"/api/Addresss/{cuenta['direccion_id']}")
    if cuenta.get("tarjeta_id"):
        pedir("GET", f"/api/Cards/{cuenta['tarjeta_id']}")
    pedir("GET", f"/api/Users/{cuenta['id']}")
    # Identificador en la ruta, objetos públicos (catálogo)
    pedir("GET", "/api/Products/3")
    pedir("GET", "/rest/products/3/reviews")
    pedir("GET", "/api/Deliverys/1")
    # Identificador en la consulta
    pedir("GET", "/api/Products/?id=3")
    pedir("GET", f"/api/Feedbacks/?UserId={cuenta['id']}")
    # Identificador en el cuerpo
    item = pedir("POST", "/api/BasketItems",
                 {"ProductId": 2, "BasketId": str(cuenta["canasta_id"]), "quantity": 1})
    captcha = pedir("GET", "/rest/captcha/")
    if captcha.get("captchaId") is not None:
        pedir("POST", "/api/Feedbacks", {"captchaId": captcha["captchaId"], "captcha": captcha.get("answer"),
                                         "comment": f"Comentario de prueba ({cuenta['correo']})",
                                         "rating": 3, "UserId": cuenta["id"]})
    # Identificador en la ruta con cuerpo (modificación de un objeto propio)
    item_id = (item.get("data") or {}).get("id")
    if item_id:
        pedir("PUT", f"/api/BasketItems/{item_id}", {"quantity": 2})


if __name__ == "__main__":
    print("1. Preparando cuentas y datos canario")
    cuentas = {nombre: preparar(nombre, correo) for nombre, correo in CUENTAS.items()}
    tokens = {nombre: iniciar_sesion(c["correo"]) for nombre, c in cuentas.items()}
    for nombre, c in cuentas.items():
        c["tarjeta_id"] = sembrar_tarjeta(nombre, tokens[nombre])
    SALIDA.write_text(json.dumps(cuentas, ensure_ascii=False, indent=2), encoding="utf-8")

    print("2. Navegando a través del proxy")
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=False, proxy={"server": PROXY},
                                      args=["--proxy-bypass-list=<-loopback>"])
        for nombre in ("A", "B"):
            navegar(navegador, nombre, CUENTAS[nombre])
        navegar(navegador, "anonima", None)
        navegador.close()

    print("3. Peticiones a la API que referencian objetos")
    for nombre, c in cuentas.items():
        llamar_api(nombre, c, tokens[nombre])

    print(f"Listo. Cuentas en {SALIDA.name}. Detén mitmdump (Ctrl+C) y ejecuta:")
    print("    python exportar_trafico.py captura_ampliada.mitm")
