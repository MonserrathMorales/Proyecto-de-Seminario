"""Prueba de concepto 2: Playwright navega Juice Shop pasando por mitmproxy.

Antes de ejecutarlo, en otra terminal (con el entorno virtual activado):
    mitmdump -p 8080 -w captura_juice.mitm
Uso:
    python prueba_captura.py [url]
Por defecto visita http://localhost:3000 (Juice Shop).
"""
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"

with sync_playwright() as p:
    navegador = p.chromium.launch(
        headless=False,
        proxy={"server": "http://127.0.0.1:8080"},
        # Chromium no envía localhost por el proxy salvo que se lo indique así
        args=["--proxy-bypass-list=<-loopback>"],
    )
    pagina = navegador.new_page()
    pagina.goto(URL)
    pagina.wait_for_timeout(5000)  # deja que la aplicación cargue sus llamadas a la API
    print("Título de la página:", pagina.title())
    navegador.close()
print("Listo. Revisa la terminal de mitmdump: deberían aparecer las peticiones GET a /rest/ y /api/.")
