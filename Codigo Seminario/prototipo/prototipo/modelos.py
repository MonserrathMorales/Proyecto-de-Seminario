"""Formatos de datos que intercambian los componentes del sistema.

Cada componente lee y escribe estos modelos, de modo que puedan probarse por separado
y que cada ejecución quede guardada como evidencia (RNF04).
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

NombreSesion = Literal["A", "B", "anonima"]


# ---------- Alcance autorizado (RF01) ----------
class CuentaPrueba(BaseModel):
    nombre: Literal["A", "B"]
    correo: str
    clave: str


class Alcance(BaseModel):
    """Lista cerrada de lo que el sistema puede tocar. Se lee de un archivo y no se modifica durante la ejecución."""
    aplicacion: str
    # Módulo que sabe preparar las cuentas y navegar esta aplicación (adaptadores.py). Por defecto Juice Shop,
    # para que los alcances anteriores a crAPI sigan siendo válidos sin editarlos.
    adaptador: Literal["juice_shop", "crapi"] = "juice_shop"
    url_base: str                              # p. ej. http://localhost:3000
    prefijos_api: list[str]                    # solo se analizan peticiones a estas rutas
    pantallas: list[str]                       # rutas de la interfaz que recorre el navegador
    cuentas: list[CuentaPrueba]
    proxy: str = "http://127.0.0.1:8080"
    vigencia_desde: date | None = None         # fechas de la autorización (RF01); sin fecha no hay límite
    vigencia_hasta: date | None = None
    autorizado_por: str = ""

    def comprobar_vigencia(self, hoy: date | None = None) -> None:
        """Detiene la ejecución si la fecha queda fuera de la autorización registrada en el alcance."""
        hoy = hoy or date.today()
        if (self.vigencia_desde and hoy < self.vigencia_desde) or (self.vigencia_hasta and hoy > self.vigencia_hasta):
            raise RuntimeError(f"La autorización del alcance no está vigente el {hoy.isoformat()} "
                               f"(desde {self.vigencia_desde}, hasta {self.vigencia_hasta}).")


# ---------- Salida del Explorador ----------
class ObjetoSembrado(BaseModel):
    """Objeto creado por el sistema en una cuenta; su dueño se conoce por construcción."""
    cuenta: Literal["A", "B"]
    tipo: str                                  # canasta, direccion, tarjeta...
    id: str
    canario: str | None = None                 # valor único sembrado, si el objeto lo tiene
    endpoint: str | None = None                # plantilla que lo entrega, p. ej. /rest/basket/{id}.
                                               # Necesaria porque el mismo id puede ser de objetos distintos


class CuentaExplorada(BaseModel):
    nombre: Literal["A", "B"]
    correo: str
    id_usuario: str                            # la clave y el token no se guardan


class PeticionCapturada(BaseModel):
    id: str                                    # p. ej. A-0007
    sesion: NombreSesion
    host: str = ""                             # p. ej. localhost:3000, para descartar tráfico ajeno al alcance
    metodo: str
    ruta: str                                  # sin la consulta
    consulta: str = ""                         # texto después de '?'
    cuerpo_peticion: str = ""
    estado: int
    tipo_contenido: str = ""
    cuerpo_respuesta: str = ""
    autenticada: bool


class ResultadoExploracion(BaseModel):
    ejecucion: str                             # identificador de la ejecución, p. ej. 20261114_1530
    fecha: datetime
    aplicacion: str
    adaptador: str = "juice_shop"              # el Analista lo usa para leer ENDPOINTS y PARAMETROS; con este
                                               # valor por defecto la evidencia anterior se sigue leyendo
    cuentas: list[CuentaExplorada]
    inventario: list[ObjetoSembrado]
    peticiones: list[PeticionCapturada]
    descartadas: dict[str, int] = Field(default_factory=dict)  # motivo -> cantidad (RF10)


# ---------- Salida del Analista ----------
Ubicacion = Literal["ruta", "consulta", "cuerpo"]


class Endpoint(BaseModel):
    """Grupo de peticiones con el mismo método, plantilla de ruta y parámetros de consulta (RF04)."""
    clave: str                                 # p. ej. "GET /rest/basket/{id}"
    metodo: str
    plantilla: str                             # ruta con los identificadores reemplazados por {id}
    parametros_consulta: list[str] = Field(default_factory=list)
    peticiones: list[str]                      # ids de las PeticionCapturada del grupo
    sesiones: list[NombreSesion]
    autenticada: bool                          # al menos una petición del grupo iba autenticada


class Candidato(BaseModel):
    """Parámetro de una petición que podría identificar un objeto. Los pasos 2 a 4 lo completan."""
    peticion: str                              # id de la PeticionCapturada
    endpoint: str                              # clave del Endpoint
    sesion: NombreSesion
    parametro: str                             # nombre (p. ej. "BasketId") o posición en la ruta
    valor: str
    ubicacion: Ubicacion
    decidido_por: Literal["inventario", "llm", "regla"] | None = None
    es_identificador: bool | None = None
    visibilidad: Literal["privado", "publico"] | None = None
    cuenta_duena: Literal["A", "B", "desconocida"] | None = None
    objeto: str | None = None                  # tipo de objeto del inventario, si corresponde
    justificacion: str = ""


class Hipotesis(BaseModel):
    """Prueba que el Agente de Validación y Remediación debe hacer: repetir una petición con otra sesión."""
    id: str                                    # p. ej. H-001
    tipo: Literal["horizontal", "sin_sesion"]  # B con objetos de A, o sin autenticación
    endpoint: str
    peticion_origen: str                       # petición original, hecha por el dueño
    sesion_origen: Literal["A", "B"]
    sesion_prueba: NombreSesion                # sesión con la que se repetirá
    cuenta_duena: Literal["A", "B", "desconocida"]
    parametro: str | None = None               # None en endpoints sin identificador (p. ej. listas propias)
    valor: str | None = None
    ubicacion: Ubicacion | None = None
    objeto: str | None = None
    origen: Literal["inventario", "llm", "regla"]  # quién decidió que el objeto es privado
    # Cómo confirmará la fuga el oráculo determinista. "sin_verificacion": el resultado quedará como dudoso
    # hasta el LLM de respaldo (Proyecto de Título).
    verificacion: Literal["canario", "inventario", "sin_verificacion"]
    canario: str | None = None                 # valor a buscar en la respuesta, si verificacion = canario
    marca_dueno: str | None = None             # id o correo del dueño a buscar, si verificacion = inventario


class ResultadoAnalisis(BaseModel):
    ejecucion: str                             # misma ejecución del Explorador
    fecha: datetime
    modo: Literal["solo_reglas", "reglas_llm"] # "solo_reglas" es la variante de la hipótesis H3
    modelo: str | None = None                  # p. ej. gemma4:e4b; None en modo solo reglas
    endpoints: list[Endpoint]
    candidatos: list[Candidato] = Field(default_factory=list)
    hipotesis: list[Hipotesis] = Field(default_factory=list)
    omitidas: dict[str, int] = Field(default_factory=dict)  # motivo -> cantidad de pruebas no generadas
    consultas_llm: int = 0
    duracion_s: float = 0.0


# ---------- Salida del Agente de Validación y Remediación ----------
class Respuesta(BaseModel):
    """Lo que devolvió la aplicación a una petición del agente. Nunca contiene tokens ni claves."""
    estado: int | None = None                  # None si la petición no llegó a responderse
    tipo_contenido: str = ""
    cuerpo: str = ""                           # con los secretos ocultos
    recortado: bool = False                    # True si el cuerpo superó el máximo y se cortó
    duracion_ms: int = 0
    error: str | None = None                   # tiempo de espera, conexión rechazada...


class ParCruzado(BaseModel):
    """Una hipótesis ejecutada: la misma petición hecha por el dueño (línea base) y por la sesión de prueba."""
    hipotesis: str                             # id de la Hipotesis, p. ej. H-001
    metodo: str = "GET"
    ruta: str = ""                             # ruta y consulta, relativas a la URL base del alcance
    sesion_base: Literal["A", "B"]
    sesion_prueba: NombreSesion
    base: Respuesta | None = None
    cruce: Respuesta | None = None
    omitida: str | None = None                 # motivo por el que no se envió (guardia de alcance)


class Remediacion(BaseModel):
    """Corrección sugerida para un hallazgo confirmado. Sale de una plantilla fija por tipo de falla, sin LLM."""
    cwe: str                                   # p. ej. CWE-639
    debilidad: str                             # nombre oficial de la debilidad en el catálogo CWE
    recomendacion: str


class Veredicto(BaseModel):
    """Clasificación de una hipótesis ejecutada (RF06)."""
    hipotesis: str
    tipo: Literal["horizontal", "sin_sesion"]
    endpoint: str
    clase: Literal["confirmado", "dudoso", "descartado"]
    motivo: str                                # código fijo, p. ej. "canario_del_dueno"
    evidencia: str = ""                        # qué se encontró: el canario, o el campo y su valor
    decidido_por: Literal["canario", "inventario", "regla"]
    remediacion: Remediacion | None = None     # solo en los hallazgos confirmados


class ResultadoValidacion(BaseModel):
    ejecucion: str                             # misma ejecución del Explorador y el Analista
    fecha: datetime
    pares: list[ParCruzado] = Field(default_factory=list)
    veredictos: list[Veredicto] = Field(default_factory=list)
    resumen: dict[str, int] = Field(default_factory=dict)   # clase -> cantidad
    enviadas: int = 0                          # peticiones realmente enviadas a la aplicación
    omitidas: dict[str, int] = Field(default_factory=dict)  # motivo -> cantidad de hipótesis no ejecutadas
    duracion_s: float = 0.0
