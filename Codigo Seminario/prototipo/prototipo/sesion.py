"""Sesión preparada y canario: lo que comparten todos los adaptadores.

Cada adaptador (juice_shop.py, crapi.py) prepara las cuentas y entrega SesionPreparada. El resto del
sistema solo usa esta clase y cabeceras(), sin saber cómo se autentica cada aplicación.
"""
import secrets
from dataclasses import dataclass, field

from prototipo.modelos import CuentaExplorada, ObjetoSembrado


@dataclass
class SesionPreparada:
    """Cuenta lista para explorar. El token vive solo en memoria y nunca se guarda en disco (RNF06).

    cabeceras_auth: cabeceras con que la aplicación reconoce la sesión, tal como las envía el navegador
    (en Juice Shop, el Bearer y la cookie "token"). Si está vacío, se usa solo el Bearer.
    """
    cuenta: CuentaExplorada
    token: str
    inventario: list[ObjetoSembrado] = field(default_factory=list)
    cabeceras_auth: dict[str, str] = field(default_factory=dict)


def cabeceras(sesion: SesionPreparada | None) -> dict[str, str]:
    """Cabeceras con que una sesión se autentica al repetir una petición; vacío si no hay sesión."""
    if sesion is None:
        return {}
    if sesion.cabeceras_auth:
        return dict(sesion.cabeceras_auth)  # copia: quien la reciba no puede cambiar la sesión
    return {"Authorization": f"Bearer {sesion.token}"}


def nuevo_canario(nombre: str) -> str:
    """Prefijo fijo y sufijo aleatorio, para que no pueda aparecer por casualidad (sección 7.3)."""
    return f"Canario-{nombre}-{secrets.token_hex(4).upper()}"
