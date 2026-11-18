"""Paso 4 del Agente de Validación y Remediación: corrección sugerida para cada hallazgo confirmado.

Usa una plantilla fija por tipo de falla, sin LLM, para que la sugerencia sea siempre la misma y no
dependa del modelo. La clasificación usa el catálogo CWE de MITRE. La redacción adaptada a cada
aplicación y la severidad CVSS 4.0 corresponden al reporte del Proyecto de Título (RF08).
"""
from prototipo.modelos import Remediacion, Veredicto

PLANTILLAS = {
    # B obtiene un objeto de A cambiando solo la sesión (IDOR/BOLA)
    "horizontal": Remediacion(
        cwe="CWE-639",
        debilidad="Authorization Bypass Through User-Controlled Key",
        recomendacion=(
            "Comprobar en el servidor, en cada petición, que el objeto solicitado pertenece al usuario "
            "autenticado: buscarlo filtrando por el usuario de la sesión además del identificador recibido, "
            "y responder 403 o 404 cuando no le pertenece. Aplicar la misma comprobación a todos los "
            "endpoints que reciben ese identificador y agregar una prueba automatizada con dos cuentas "
            "que verifique que una no puede leer los objetos de la otra.")),
    # Un endpoint privado responde sin autenticación
    "sin_sesion": Remediacion(
        cwe="CWE-306",
        debilidad="Missing Authentication for Critical Function",
        recomendacion=(
            "Exigir autenticación en el endpoint y responder 401 cuando la petición no trae una sesión "
            "válida. Aplicar el control de autenticación por defecto a todas las rutas privadas, de modo "
            "que una ruta nueva quede protegida aunque nadie lo recuerde, y agregar una prueba "
            "automatizada que verifique que el endpoint rechaza las peticiones sin sesión.")),
}


def sugerir(v: Veredicto) -> Remediacion | None:
    """Solo los hallazgos confirmados llevan corrección; un resultado dudoso o descartado no la necesita."""
    return PLANTILLAS.get(v.tipo) if v.clase == "confirmado" else None
