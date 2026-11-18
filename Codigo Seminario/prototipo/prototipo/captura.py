"""Paso 3 del Explorador: inicia mitmproxy, navega con Playwright y recoge el tráfico.

A diferencia de la prueba de concepto, aquí el propio Explorador arranca y detiene la captura,
etiqueta cada petición con su sesión y entrega las peticiones como objetos PeticionCapturada.
La combinación de Playwright y mitmproxy es la validada por A2CT (Schlaubitz et al., 2025).
"""
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from mitmproxy import http, io
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from prototipo.juice_shop import SesionPreparada
from prototipo.modelos import Alcance, PeticionCapturada

ESPERA_PANTALLA = 3000  # ms por pantalla, para que termine sus llamadas a la API
CABECERA_SESION = "X-Sesion"  # etiqueta que agrega el navegador; no la envía la aplicación


def _puerto_abierto(puerto: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _arrancar_proxy(puerto: int, archivo: Path) -> subprocess.Popen:
    """Arranca mitmdump en segundo plano y espera a que abra el puerto."""
    ejecutable = shutil.which("mitmdump")
    if ejecutable is None:
        raise RuntimeError("No se encontró mitmdump. ¿Está activado el entorno virtual con mitmproxy instalado?")
    if _puerto_abierto(puerto):  # otro proceso ya escucha ahí (p. ej. un mitmdump que quedó abierto)
        raise RuntimeError(f"El puerto {puerto} ya está en uso. Cierra el mitmdump o programa que lo ocupa "
                           f"y vuelve a intentar.")
    registro = archivo.with_suffix(".log")  # stderr de mitmdump, para ver el motivo si algo falla
    with registro.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen([ejecutable, "-p", str(puerto), "-w", str(archivo), "-q"],
                                stdout=subprocess.DEVNULL, stderr=err)
    for _ in range(20):  # espera hasta 10 s a que el proxy quede escuchando
        if proc.poll() is not None:  # primero: ¿el proceso murió?
            motivo = registro.read_text(encoding="utf-8").strip() or "sin mensaje"
            raise RuntimeError(f"mitmdump no pudo iniciarse: {motivo}")
        if _puerto_abierto(puerto):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"mitmdump no abrió el puerto {puerto} en 10 s. Revisa {registro}")


def pantallas_de(alcance: Alcance, preparada: SesionPreparada | None) -> list[str]:
    """Completa las pantallas con ids del inventario, p. ej. /#/address/edit/{direccion} -> /#/address/edit/7.

    Las pantallas con un id que la sesión no tiene (o la sesión anónima) se omiten.
    """
    ids = {o.tipo: o.id for o in preparada.inventario} if preparada else {}
    rutas = []
    for ruta in alcance.pantallas:
        try:
            rutas.append(ruta.format(**ids))
        except KeyError:
            continue
    return rutas


def _navegar(navegador, alcance: Alcance, sesion: str, cuenta, preparada: SesionPreparada | None = None) -> None:
    """Recorre las pantallas del alcance con una sesión. cuenta es None para la sesión anónima."""
    ctx = navegador.new_context(extra_http_headers={CABECERA_SESION: sesion})
    ctx.add_cookies([{"name": n, "value": "dismiss", "url": alcance.url_base}
                     for n in ("welcomebanner_status", "cookieconsent_status")])  # tapan el formulario
    pagina = ctx.new_page()
    if cuenta is not None:
        pagina.goto(f"{alcance.url_base}/#/login")
        pagina.fill("#email", cuenta.correo)
        pagina.fill("#password", cuenta.clave)
        pagina.click("#loginButton")
        try:
            pagina.wait_for_url("**/#/search", timeout=10000)
        except PlaywrightTimeout:
            print(f"   AVISO: la sesión {sesion} no llegó a la página principal; revisa el inicio de sesión.")
    rutas = pantallas_de(alcance, preparada)
    for ruta in rutas:
        pagina.goto(f"{alcance.url_base}{ruta}")
        pagina.wait_for_timeout(ESPERA_PANTALLA)
    print(f"   Sesión {sesion}: {len(rutas)} pantallas recorridas")
    ctx.close()


def _leer_captura(archivo: Path) -> list[PeticionCapturada]:
    """Convierte el archivo de mitmproxy en peticiones, sin filtrar todavía (el filtro va en el paso 4)."""
    peticiones, n = [], 0
    with archivo.open("rb") as f:
        for flujo in io.FlowReader(f).stream():
            if not isinstance(flujo, http.HTTPFlow) or flujo.response is None:
                continue
            pet, res = flujo.request, flujo.response
            n += 1
            peticiones.append(PeticionCapturada(
                id=f"{pet.headers.get(CABECERA_SESION, '?')}-{n:04d}",
                sesion=pet.headers.get(CABECERA_SESION, "anonima"),
                host=f"{pet.host}:{pet.port}",
                metodo=pet.method, ruta=pet.path.split("?")[0],
                consulta=pet.path.split("?", 1)[1] if "?" in pet.path else "",
                cuerpo_peticion=pet.get_text(strict=False) or "",
                estado=res.status_code, tipo_contenido=res.headers.get("content-type", ""),
                cuerpo_respuesta=res.get_text(strict=False) or "",
                autenticada="Authorization" in pet.headers))
    return peticiones


def capturar(alcance: Alcance, sesiones: dict[str, SesionPreparada]) -> list[PeticionCapturada]:
    """Navega como A, B y anónima a través del proxy, y devuelve todo el tráfico capturado."""
    puerto = int(alcance.proxy.rsplit(":", 1)[1])
    archivo = Path(tempfile.gettempdir()) / f"captura_{int(time.time())}.mitm"
    try:
        proxy = _arrancar_proxy(puerto, archivo)
        try:
            with sync_playwright() as p:
                navegador = p.chromium.launch(headless=False, proxy={"server": alcance.proxy},
                                              args=["--proxy-bypass-list=<-loopback>"])  # fuerza localhost por el proxy
                for cuenta in alcance.cuentas:
                    _navegar(navegador, alcance, cuenta.nombre, cuenta, sesiones.get(cuenta.nombre))
                _navegar(navegador, alcance, "anonima", None)
                navegador.close()
        finally:
            proxy.terminate()
            proxy.wait(timeout=10)
        return _leer_captura(archivo)
    finally:
        # El archivo de mitmproxy contiene las claves y los tokens sin ocultar: se borra siempre,
        # también cuando la navegación o la lectura fallan (RNF06).
        try:
            archivo.unlink(missing_ok=True)
        except OSError:
            print(f"   AVISO: no se pudo borrar {archivo}; bórralo a mano, contiene tokens.")
