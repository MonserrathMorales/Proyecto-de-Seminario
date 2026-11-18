"""Elige el adaptador de la aplicación evaluada según el campo "adaptador" del alcance.

Todo adaptador es un módulo que expone la misma interfaz:
  - verificar_disponible(url_base): falla con un mensaje claro si la aplicación no responde;
  - preparar(alcance) -> dict[str, SesionPreparada]: registra las cuentas y siembra los objetos canario;
  - preparar_contexto(ctx, alcance): ajustes del navegador antes de navegar (cookies, avisos);
  - iniciar_sesion_navegador(pagina, alcance, cuenta): inicio de sesión en la interfaz;
  - ENDPOINTS: tipo de objeto -> plantilla de la ruta que lo entrega;
  - PARAMETROS: nombre del parámetro en minúsculas -> tipo de objeto.
La importación es diferida: elegir Juice Shop no carga el código de crAPI, ni al revés.
"""
import importlib
from types import ModuleType

MODULOS = {"juice_shop": "prototipo.juice_shop", "crapi": "prototipo.crapi"}
INTERFAZ = ("verificar_disponible", "preparar", "preparar_contexto", "iniciar_sesion_navegador",
            "ENDPOINTS", "PARAMETROS")


def adaptador_de(nombre: str) -> ModuleType:
    if nombre not in MODULOS:
        raise ValueError(f"No hay adaptador para '{nombre}'. Opciones: {', '.join(MODULOS)}")
    return importlib.import_module(MODULOS[nombre])
