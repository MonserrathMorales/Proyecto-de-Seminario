"""Aplicación simulada para probar sin Juice Shop. La usan verificar_validacion.py y verificar_orquestador.py.

Sustituye a requests: solo sabe hacer GET, contesta con las respuestas que el Explorador ya guardó y
anota cada llamada que recibe. Simula la falla documentada de Juice Shop (entrega la canasta a cualquier
cuenta autenticada) y protege todo lo demás.
"""
from prototipo.cruce import ruta_relativa
from prototipo.modelos import ResultadoExploracion


class RespuestaSimulada:
    def __init__(self, estado: int, texto: str):
        self.status_code, self.text, self.headers = estado, texto, {"content-type": "application/json"}


class AplicacionSimulada:
    def __init__(self, r: ResultadoExploracion, url_base: str, tokens: dict[str, str], modo: str = "canasta_vulnerable"):
        self.url_base, self.modo = url_base.rstrip("/"), modo
        self.sesion_de = {token: nombre for nombre, token in tokens.items()}
        self.propias = {(p.sesion, ruta_relativa(p)): p.cuerpo_respuesta for p in r.peticiones if p.estado == 200}
        self.duena = {ruta: sesion for (sesion, ruta) in self.propias if sesion in ("A", "B")}
        self.llamadas: list[dict] = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        headers = dict(headers or {})
        sesion = self.sesion_de.get(headers.get("Authorization", "").removeprefix("Bearer "), "anonima")
        ruta = url[len(self.url_base):]
        self.llamadas.append({"url": url, "ruta": ruta, "sesion": sesion, "cabeceras": headers,
                              "redirecciones": allow_redirects})
        if self.modo == "tokens_vencidos":
            return RespuestaSimulada(401, '{"error": "sesión vencida"}')
        if sesion == "anonima":
            if ruta.startswith("/rest/user/whoami"):
                return RespuestaSimulada(200, '{"user": {}}')
            return RespuestaSimulada(401, '{"error": "No Authorization header was found"}')
        if (sesion, ruta) in self.propias:                      # la cuenta pide algo suyo
            return RespuestaSimulada(200, self.propias[(sesion, ruta)])
        if ruta.startswith("/rest/basket/") and ruta in self.duena:   # falla simulada: canasta de otra cuenta
            return RespuestaSimulada(200, self.propias[(self.duena[ruta], ruta)])
        return RespuestaSimulada(403, '{"status": "error", "message": "no autorizado"}')
