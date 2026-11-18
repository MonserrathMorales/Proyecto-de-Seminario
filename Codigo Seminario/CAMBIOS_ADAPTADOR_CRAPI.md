# Adaptador de crAPI: resumen de cambios

Fecha: 17 de noviembre de 2026; prueba con crAPI real el 18 de noviembre. Respaldo previo: `Seminario/prototipo_respaldo_20261117_2236.zip` (32 archivos: `prototipo/`, `verificar_*.py`, `simulacion.py`, `demo_explorador.py`, `alcance_juice.json`; sin `.venv/`, `datos/` ni `__pycache__/`). No se hicieron commits ni se editaron el informe ni `ARQUITECTURA.md`.

**Resultado:** el prototipo elige el adaptador según el alcance. Con Juice Shop, los seis verificadores dan exactamente la misma salida que antes. Con **crAPI real** (18/11), el flujo completo explorador → analista → validacion → cerrar **confirmó el desafío BOLA 2 en ambas direcciones** (B lee el reporte de mecánico de A, y A el de B) por canario, descartó las pruebas sin sesión y no guardó ningún token. Dio el mismo resultado en los dos modos del Analista: `solo_reglas` (`prototipo/datos/20261118_004635/`) y `reglas_llm` con `gemma4:e4b` (`prototipo/datos/20261118_005934/`).

## 1. Archivos creados o modificados

| Archivo | Cambio |
|---|---|
| `prototipo/sesion.py` | **Nuevo.** `SesionPreparada` (con el campo opcional `cabeceras_auth`), `cabeceras()` y `nuevo_canario()`, comunes a los adaptadores |
| `prototipo/adaptadores.py` | **Nuevo.** `adaptador_de(nombre)` con importación diferida y la lista de la interfaz (`INTERFAZ`) |
| `prototipo/crapi.py` | **Nuevo.** Adaptador de crAPI: registro, login, vehículo (VIN desde MailHog), reporte de mecánico con canario, login en la interfaz |
| `prototipo/juice_shop.py` | Reexporta `SesionPreparada`, `cabeceras` y `nuevo_canario`; `preparar_cuenta` llena `cabeceras_auth` con el Bearer y la cookie `token`; recibe `preparar_contexto()` e `iniciar_sesion_navegador()` desde `captura.py` |
| `prototipo/modelos.py` | `Alcance.adaptador` (`"juice_shop"` por defecto) y `ResultadoExploracion.adaptador` (`"juice_shop"` por defecto, para leer la evidencia antigua) |
| `prototipo/captura.py` | Sin código de Juice Shop: usa `preparar_contexto()` e `iniciar_sesion_navegador()` del adaptador del alcance |
| `prototipo/explorador.py` | Prepara las cuentas con el adaptador del alcance y guarda su nombre en la evidencia |
| `prototipo/cruce.py` | `enviar()` usa `sesion.cabeceras()`; ya no importa `juice_shop` |
| `prototipo/propiedad.py` | `Inventario(objetos, adaptador="juice_shop")` lee `ENDPOINTS` y `PARAMETROS` del adaptador de la evidencia |
| `prototipo/analista.py` | Una línea: pasa `r.adaptador` al inventario. La firma de `analizar()` no cambia |
| `prototipo/grafo.py`, `prototipo/validacion.py` | Importan `SesionPreparada` desde `sesion.py` |
| `alcance_crapi.json` | **Nuevo.** Alcance de crAPI (ver sección 3 por los correos `@example.com`) |
| `verificar_adaptadores.py` | **Nuevo.** 12 criterios sin servicios |
| `probar_crapi.py` | **Nuevo.** Prueba con crAPI levantado; con `--grafo`, el flujo completo (por defecto `solo_reglas`; con `--modo reglas_llm`, con el modelo) |
| `preparar_y_probar_crapi.bat` / `.ps1` | **Nuevos.** Rehacen el `.venv` si no funciona en el equipo, instalan `requirements.txt` y Chromium, y corren `verificar_adaptadores.py` y `probar_crapi.py`. Salida en `preparar_y_probar_crapi.txt` |
| `probar_crapi_grafo.bat` / `.ps1` | **Nuevos.** Corren `probar_crapi.py --grafo` con el `.venv` en el PATH (para encontrar `mitmdump`). Salida en `probar_crapi_grafo.txt` |
| `probar_crapi_grafo_llm.bat` / `.ps1` | **Nuevos.** Como el anterior, en modo `reglas_llm`; antes revisan que Ollama responda y tenga `gemma4:e4b`. Salida en `probar_crapi_grafo_llm.txt` |
| `diagnostico_crapi.bat` | **Nuevo**, no se usó: revisa Python, Docker, RAM y puertos sin instalar nada |
| `.venv` | **Rehecho** en este equipo (`--clear`) con Python 3.13.17 del usuario `freec`: el anterior apuntaba a `C:\Users\A\...` y no tenía `mitmproxy` ni `playwright` |

No se tocó el núcleo (`filtro.py`, `extraccion.py`, `endpoints.py`, `hipotesis.py`, `oraculo.py`, `remediacion.py`, `clasificador.py`) ni ningún verificador existente.

**Único cambio de comportamiento, y no afecta a Juice Shop real:** una `SesionPreparada` creada a mano sin `cabeceras_auth` (solo la crean los verificadores, con tokens simulados) envía ahora solo `Authorization: Bearer`, sin la cookie `token`. Las sesiones que prepara `juice_shop.preparar_cuenta` siguen enviando ambas. `simulacion.py` reconoce la sesión por el Bearer, así que las salidas no cambian.

## 2. Salida de los verificadores

| Verificador | Línea base (antes) | Después de A, B y C | Salida |
|---|---|---|---|
| `verificar_validacion.py` | 14 OK, 0 FALLA | 14 OK, 0 FALLA | Idéntica |
| `verificar_orquestador.py` | 11 OK, 0 FALLA | 11 OK, 0 FALLA | Idéntica |
| `verificar_analista_paso1.py` | 6 OK, 0 FALLA | 6 OK, 0 FALLA | Idéntica |
| `verificar_analista_paso2.py` | 6 OK, 0 FALLA | 6 OK, 0 FALLA | Idéntica |
| `verificar_analista_paso3.py` | 5 OK, 0 FALLA | 5 OK, 0 FALLA | Idéntica |
| `verificar_analista_paso5.py` | 7 OK, 0 FALLA | 7 OK, 0 FALLA | Idéntica |
| `verificar_adaptadores.py` (nuevo) | — | 12 OK, 0 FALLA | — |

"Idéntica" significa que `diff` entre ambas salidas no muestra diferencias (salvo las duraciones en segundos). Todos usan la evidencia `datos/20261117_162744/exploracion.json`.

### `python verificar_validacion.py` (igual antes y después)

```
Parte 1. Evidencia: datos/20261117_162744/exploracion.json (se trabaja sobre una copia temporal)

 Id    Tipo       Endpoint                      Valor Prueba   Veredicto   Motivo
 H-001 horizontal GET /rest/basket/{id}         6     B        confirmado  marca_del_dueno_en_el_mismo_campo  [data.UserId = 25]
 H-002 sin_sesion GET /rest/basket/{id}         6     anonima  descartado  acceso_denegado
 H-003 horizontal GET /api/Addresss/{id}        7     B        descartado  acceso_denegado
 H-004 sin_sesion GET /api/Addresss/{id}        7     anonima  descartado  acceso_denegado
 H-005 horizontal GET /rest/basket/{id}         7     A        confirmado  marca_del_dueno_en_el_mismo_campo  [data.UserId = 26]
 H-006 sin_sesion GET /rest/basket/{id}         7     anonima  descartado  acceso_denegado
 H-007 horizontal GET /api/Addresss/{id}        8     A        descartado  acceso_denegado
 H-008 sin_sesion GET /api/Addresss/{id}        8     anonima  descartado  acceso_denegado
 H-009 sin_sesion GET /rest/user/whoami?fields  -     anonima  descartado  respuesta_sin_datos_del_dueno
 H-010 sin_sesion GET /api/Addresss             -     anonima  descartado  acceso_denegado
 H-011 sin_sesion GET /api/Cards                -     anonima  descartado  acceso_denegado

 Resumen: {'confirmado': 2, 'dudoso': 0, 'descartado': 9}   Peticiones enviadas: 18   Omitidas: ninguna
 Corrección sugerida para H-001 (CWE-639): Comprobar en el servidor, en cada petición, que el objeto solicitado pertenece al usuario auten...
 Corrección sugerida para H-005 (CWE-639): Comprobar en el servidor, en cada petición, que el objeto solicitado pertenece al usuario auten...

[OK] Solo se envían GET a la URL base del alcance, sin seguir redirecciones
[OK] Solo se repiten peticiones que el Explorador observó, sin cambiar ningún identificador
[OK] Cada hipótesis se envía una vez con el dueño (línea base) y una con la sesión de prueba
[OK] Las pruebas sin sesión no llevan ninguna credencial
[OK] La canasta de otra cuenta queda confirmada por el campo del dueño
[OK] Lo protegido y lo pedido sin sesión queda descartado, sin dudosos
[OK] Solo los hallazgos confirmados llevan corrección sugerida (CWE-639)
[OK] La guardia rechaza escrituras, otros servidores, otras rutas y orígenes fallidos sin enviar nada
[OK] Con la autorización vencida no se envía ninguna petición
[OK] Con los tokens vencidos todo queda dudoso y nada se da por protegido
[OK] La marca del dueño no se busca como texto: '26' dentro de '2026' no confirma una fuga
[OK] El canario confirma la fuga aunque el código sea de error, y su ausencia la descarta
[OK] La evidencia guardada no contiene tokens
[OK] La validación se guarda y se lee sin pérdida
```

### `python verificar_orquestador.py` (igual antes y después)

```
Evidencia que entrega el Explorador simulado: datos/20261117_162744/exploracion.json

Nodos del grafo: ['explorador', 'analista', 'validacion', 'cerrar']

1. Corrida normal
   explorador  ok       0.0 s  {'conservadas': 49, 'descartadas': {'recurso_estatico': 133, 'fuera_del_alcance': 2, 'sin_contenido': 24, 'duplicada': 4, 'websocket': 3}, 'por_sesion': {'A': 18, 'B': 18, 'anonima': 13}, 'inventario': 10}
   analista    ok       0.0 s  {'modo': 'solo_reglas', 'endpoints': 18, 'candidatos': 4, 'por_inventario': 4, 'consultas_llm': 0, 'hipotesis': 11, 'omitidas': {'sin_datos_propios': 6}}
   validacion  ok       0.0 s  {'hipotesis': 11, 'enviadas': 18, 'omitidas': {}, 'confirmado': 2, 'dudoso': 0, 'descartado': 9}
   cerrar      ok       0.0 s  {}

2. Falla el Explorador   -> etapas ['explorador', 'cerrar']   error: Explorador: aplicación inalcanzable (simulado)
3. Falla el Analista     -> etapas ['explorador', 'analista', 'cerrar']   error: Analista: Ollama no responde (simulado)
4. Falla la Validación   -> etapas ['explorador', 'analista', 'validacion', 'cerrar']   error: Validación: autorización vencida (simulado)

[OK] El grafo tiene los cuatro nodos
[OK] Las cuatro etapas corrieron en orden y terminaron bien
[OK] Cada agente recibió la evidencia del anterior y dejó la suya
[OK] El resumen del estado coincide con la evidencia guardada
[OK] El registro guardado tiene las cuatro etapas y ningún error
[OK] Ni el estado del grafo, ni el registro, ni la validación contienen tokens
[OK] Las sesiones se liberaron de la memoria al cerrar
[OK] Si falla el Explorador, el flujo salta a cerrar y no analiza ni valida
[OK] Si falla el Analista, el flujo salta a cerrar y no se envía ninguna petición
[OK] Si falla la Validación, el error queda registrado y el flujo cierra
[OK] En las tres fallas las sesiones también se liberan de la memoria
```

### `python verificar_adaptadores.py`

```
Interfaz que falta en cada adaptador: {'juice_shop': [], 'crapi': []}
Cabeceras de Juice Shop: ['Authorization', 'Cookie']; sin sesión: {}
Pantallas de crAPI con reporte: ['/dashboard', '/my-profile', '/vehicle-service-dashboard', '/service-report?id=5', '/past-orders', '/shop', '/forum']
Marcas en el código fuera de los adaptadores: ninguna
   (solo como ejemplo en docstrings o comentarios: endpoints.py, modelos.py, propiedad.py)
   crAPI, cuenta A: registrada, id 11, vehículo 0b1c2d3e-0000-4000-8000-000000000000, reporte 5
   crAPI, cuenta B: registrada, id 12, vehículo 0b1c2d3e-0000-4000-8000-000000000001, reporte 6
   inventario: A vehiculo 0b1c2d3e-0000-4000-8000-000000000000  Canario-A-279C734F   /identity/api/v2/vehicle/{id}/location
   inventario: A reporte  5                                     Canario-A-776F80EC   /workshop/api/mechanic/mechanic_report
   inventario: B vehiculo 0b1c2d3e-0000-4000-8000-000000000001  Canario-B-7EB65D8C   /identity/api/v2/vehicle/{id}/location
   inventario: B reporte  6                                     Canario-B-6B40D0EE   /workshop/api/mechanic/mechanic_report
Analista con crAPI: candidato report_id=5 -> inventario, dueña A, objeto reporte; hipótesis H-001: B pide el reporte de A, verificación canario Canario-A-776F80EC

[OK] alcance_juice.json elige juice_shop y alcance_crapi.json elige crapi
[OK] adaptador_de() entrega toda la interfaz para ambos adaptadores
[OK] Una sesión sin cabeceras propias envía solo el Bearer, y sin sesión no envía nada
[OK] La sesión de Juice Shop sigue enviando el Bearer y la cookie token, y la anónima nada
[OK] pantallas_de() completa /service-report?id=<id> y lo omite si no hay reporte
[OK] El filtro y ruta_relativa() conservan la consulta del reporte
[OK] Fuera de los adaptadores no hay rutas, selectores ni cookies de una aplicación
[OK] crAPI: A y B quedan con vehículo (VIN leído de MailHog) y reporte con canario
[OK] crAPI: si el mecánico no conecta por localhost, se usa la red interna de Docker
[OK] crAPI: la sesión envía solo el Bearer y ningún token aparece en lo impreso
[OK] Analista: el report_id de la consulta se asigna a su dueña con el inventario, sin modelo
[OK] Oráculo: B leyendo el reporte de A se confirma por canario; con 403 se descarta
```

### `python probar_crapi.py` con crAPI real (18/11, `preparar_y_probar_crapi.txt`)

Los 10 contenedores de crAPI estaban `healthy` (chatbot `Up`). En este equipo, `verificar_adaptadores.py` también dio 12 `[OK]`.

```
Parte 1. Preparación de cuentas en http://localhost:8888 (MailHog en http://localhost:8025)
   crAPI, cuenta A: registrada, id 8, vehículo 74c9555b-9905-46e0-a3c5-3b68ce589322, reporte 6
   crAPI, cuenta B: registrada, id 9, vehículo 4cd00fc3-bcab-4c79-88a9-d96f46bb0919, reporte 7
 Peticiones de preparación (no pasan por el proxy):
   GET  /identity/health_check                    200  {"message": "Okay", "status": 200}
   POST /identity/api/auth/signup                 200  {"message": "User registered successfully! Please Login.", "status": 200}
   POST /identity/api/auth/login                  200  {"token": "***", "type": "Bearer", "message": "Login successful", ...}
   GET  /identity/api/v2/user/dashboard           200  {"id": 8, "name": "Titular Canario-A-C9702320", "email": "a.canario@example.com", ...}
   GET  /identity/api/v2/vehicle/vehicles         200  []
   GET  /api/v2/search                            200  1 correos encontrados
   POST /identity/api/v2/vehicle/add_vehicle      200  {"message": "Vehicle save successfully..", "status": 200}
   POST /workshop/api/merchant/contact_mechanic   200  {"response_from_mechanic_api": {"id": 6, "sent": true, "report_link": ...}}
   (… lo mismo para B …)
[OK] crAPI, identity, workshop y MailHog responden
[OK] A y B tienen vehículo y reporte en el inventario
[OK] El reporte guarda su canario y crAPI lo devuelve en mechanic_report
[OK] Ningún token aparece en lo impreso
```

En la segunda ejecución, el registro respondió `403 "Number already registered!"` y el adaptador siguió con el login, como se esperaba.

### `python probar_crapi.py --grafo` con crAPI real

**Primera corrida (`datos/20261118_003854`): 2 `[OK]` y 3 `[FALLA]`.** El Explorador solo capturó el login y el dashboard de cada cuenta. Causa: crAPI guarda la sesión del navegador en `localStorage` (redux-persist, clave `persist:reducers`) con un pequeño retraso. El Explorador recargaba la primera pantalla antes de que quedara guardada, y crAPI redirigía a `/login` sin pedir datos (`components/layout/layout.tsx`). Uno de los `[FALLA]` era un falso positivo: el criterio buscaba la palabra `Bearer`, y crAPI la devuelve en `"type": "Bearer"` junto a `"token": "***"`; no había tokens en la evidencia. Correcciones: `crapi.iniciar_sesion_navegador()` espera `isLoggedIn = true` en `persist:reducers` y que el dashboard termine sus llamadas; el criterio busca tokens reales (`Bearer <token>` o `eyJ…`).

**Segunda corrida (`datos/20261118_004635`): 5 `[OK]`.**

```
   Sesión A: 7 pantallas recorridas
   Sesión B: 7 pantallas recorridas
   Sesión anonima: 6 pantallas recorridas
   explorador  ok   112.3 s  {'conservadas': 20, 'descartadas': {'fuera_del_alcance': 2, 'recurso_estatico': 89, 'duplicada': 7}, 'por_sesion': {'A': 10, 'B': 10, 'anonima': 0}, 'inventario': 4}
   analista    ok     0.0 s  {'modo': 'solo_reglas', 'endpoints': 10, 'candidatos': 4, 'por_inventario': 2, 'consultas_llm': 0, 'hipotesis': 5, 'omitidas': {'sin_datos_propios': 5}}
   validacion  ok    21.4 s  {'hipotesis': 5, 'enviadas': 8, 'omitidas': {}, 'confirmado': 2, 'dudoso': 0, 'descartado': 3}
   cerrar      ok     0.0 s  {}
 Endpoints observados:
   POST /identity/api/auth/login                                  A,B
   GET /identity/api/v2/user/dashboard                            A,B
   POST /identity/api/auth/verify                                 A,B
   GET /identity/api/v2/vehicle/vehicles                          A,B
   GET /identity/api/v2/user/videos/{id}                          A,B
   GET /workshop/api/merchant/service_requests/null               A,B
   GET /workshop/api/mechanic/mechanic_report?report_id           A,B
   GET /workshop/api/shop/orders/all?limit&offset                 A,B
   GET /workshop/api/shop/products?limit&offset                   A,B
   GET /community/api/v2/community/posts/recent?limit&offset      A,B
 Id    Tipo       Endpoint                                   Objeto   Prueba   Veredicto   Motivo
 H-001 horizontal GET /workshop/api/mechanic/mechanic_report reporte  B        confirmado  canario_del_dueno  [Canario-A-81FED5AF]
 H-002 sin_sesion GET /workshop/api/mechanic/mechanic_report reporte  anonima  descartado  acceso_denegado
 H-003 horizontal GET /workshop/api/mechanic/mechanic_report reporte  A        confirmado  canario_del_dueno  [Canario-B-CBD2B907]
 H-004 sin_sesion GET /workshop/api/mechanic/mechanic_report reporte  anonima  descartado  acceso_denegado
 H-005 sin_sesion GET /identity/api/v2/user/dashboard         -        anonima  descartado  acceso_denegado
 Resumen: {'confirmado': 2, 'dudoso': 0, 'descartado': 3}   Peticiones enviadas: 8   Omitidas: ninguna
 Ubicación del vehículo (BOLA 1) en la evidencia: 0 peticiones (esperable: solo se pide al pulsar Refresh Location)
[OK] El grafo ejecutó explorador, analista, validacion y cerrar
[OK] El reporte de mecánico de una cuenta, pedido por la otra, queda confirmado (BOLA 2)
[OK] Las pruebas sin sesión del reporte quedan descartadas
[OK] Ni datos/<ejecucion>/ ni el estado del grafo contienen tokens (Bearer <token> ni eyJ)
[OK] Las sesiones se liberaron de la memoria al cerrar
```

Candidatos: los dos `report_id` (14 de A, 15 de B) los resolvió el **inventario**. Los dos `videos/0` (crAPI pide el video 0 cuando la cuenta no tiene ninguno; responde 404) quedaron **pendientes**: en `solo_reglas` se descartan sin decidir ("fuera del inventario; sin LLM no se puede decidir"), aunque en el registro figuran como `regla`.

### `python probar_crapi.py --grafo --modo reglas_llm` con crAPI real (`datos/20261118_005934`): 9 `[OK]`

Ollama respondió con `gemma4:e4b`, `qwen3.5:9b` y `qwen3.5:4b`. Las 4 comprobaciones de la parte 1 y las 5 del flujo dieron `[OK]`.

```
   explorador  ok   111.0 s  {'conservadas': 20, 'descartadas': {'fuera_del_alcance': 2, 'recurso_estatico': 87, 'duplicada': 7}, 'por_sesion': {'A': 10, 'B': 10, 'anonima': 0}, 'inventario': 4}
   analista    ok    39.6 s  {'modo': 'reglas_llm', 'endpoints': 10, 'candidatos': 4, 'por_inventario': 2, 'consultas_llm': 2, 'hipotesis': 5, 'omitidas': {'sin_datos_propios': 5}}
   validacion  ok    21.4 s  {'hipotesis': 5, 'enviadas': 8, 'omitidas': {}, 'confirmado': 2, 'dudoso': 0, 'descartado': 3}
   cerrar      ok     0.0 s  {}
 H-001 horizontal GET /workshop/api/mechanic/mechanic_report reporte  B        confirmado  canario_del_dueno  [Canario-A-5C7778F9]
 H-002 sin_sesion GET /workshop/api/mechanic/mechanic_report reporte  anonima  descartado  acceso_denegado
 H-003 horizontal GET /workshop/api/mechanic/mechanic_report reporte  A        confirmado  canario_del_dueno  [Canario-B-8B9DFC76]
 H-004 sin_sesion GET /workshop/api/mechanic/mechanic_report reporte  anonima  descartado  acceso_denegado
 H-005 sin_sesion GET /identity/api/v2/user/dashboard         -        anonima  descartado  acceso_denegado
 Analista: modo reglas_llm, modelo gemma4:e4b, consultas al modelo 2, 39.6 s
   candidato A  videos=0       llm         es_identificador = false
   candidato A  report_id=18   inventario  dueña A, reporte sembrado en la cuenta A
   candidato B  videos=0       llm         es_identificador = false
   candidato B  report_id=19   inventario  dueña B, reporte sembrado en la cuenta B
```

El modelo decidió que `videos/0` **no es un identificador**. Justificación de A: el valor 0 no identifica un registro concreto de usuario, y la respuesta 404 indica que el recurso no existe. Coincide con lo correcto: crAPI usa 0 cuando la cuenta no tiene video.

**Comparación de modos (para H3):**

| | `solo_reglas` | `reglas_llm` |
|---|---|---|
| Candidatos / por inventario / pendientes | 4 / 2 / 2 | 4 / 2 / 2 |
| Cómo se resolvieron los pendientes | Descartados sin decidir | El LLM decidió que no son identificadores (correcto) |
| Consultas al modelo / duración del Analista | 0 / 0,0 s | 2 / 39,6 s |
| Hipótesis / confirmados / descartados | 5 / 2 / 3 | 5 / 2 / 3 |

Con crAPI, el LLM no cambió el resultado: los dos pendientes eran un falso candidato que ambos modos dejan fuera, uno por descarte y otro por decisión del modelo. Costó 39,6 s más.

## 3. Datos de crAPI

Leídos en el **código fuente** de `crAPI-main` 1.1.5 y **confirmados con crAPI corriendo** el 18/11 (salida de `probar_crapi.py`), salvo donde se indica.

| Dato | Valor | Fuente |
|---|---|---|
| **Correo del VIN** | Solo llega a MailHog si el correo termina en **`@example.com`** (`MAILHOG_DOMAIN=example.com`). Con otro dominio, crAPI lo envía a `smtp.example.com`, falla sin aviso y el vehículo no se puede agregar. Por eso las cuentas son `a.canario@example.com` y `b.canario@example.com`, no `@prueba.cl` | `deploy/docker/docker-compose.yml`, `utils/SMTPMailServer.java` |
| Formato del correo | Real: HTML en **quoted-printable**, asunto "Welcome to crAPI"; texto `VIN: TS62SL366MGHSL9B4 and Pincode: 0696`. En el código: `VIN: </font><font …>XXXXXXXXXXXXXXXXX</font></b> and <b>Pincode: <font …>1234</font>`. El adaptador decodifica el MIME (quoted-printable o base64), quita las etiquetas y aplica `VIN:\s*([A-Z0-9]{17})` y `Pincode:\s*(\d{3,6})` | `utils/MailBody.java`, `utils/GenerateVIN.java` (VIN de 17, pincode de 4 dígitos) |
| Registro | `name` de 3 a 100 caracteres, sin restricción de caracteres (acepta `Titular Canario-A-1A2B3C4D`); `password` de 6 a 100; `number` de hasta 15 y **único por usuario** (se deriva del correo con SHA-256, para que sea el mismo en cada ejecución) | `model/SignUpForm.java`, `UserRegistrationServiceImpl.java` |
| Cuenta existente | El registro responde 403 y el adaptador sigue con el login | `UserRegistrationServiceImpl.java` |
| Dashboard | Real: campos `available_credit, email, id, name, number, picture_url, role, video_id, video_name, video_url`; el id del usuario va en `"id"` (A = 8, B = 9). El nombre **aceptó el canario** (`Titular Canario-A-C9702320`) | `model/DashboardResponse.java` |
| `report_link` | Real: `{"response_from_mechanic_api":{"id":6,"sent":true,"report_link":"http://localhost:8888/workshop/api/mechanic/mechanic_report?report_id=6"},"status":200}`. Se usa `id` y, si falta, el `report_id` de la consulta | `workshop/crapi/mechanic/views.py`, `merchant/views.py` |
| `mechanic_api` | Funcionó al primer intento con `http://localhost:8888/...`; el respaldo `http://crapi-web/...` no hizo falta, pero se mantiene | Corrida del 18/11 |
| `mechanic_report` | Pide JWT y devuelve `problem_details`, donde va el canario | `MechanicServiceRequestSerializer` |
| Ubicación (BOLA 1) | Devuelve `carId`, `vehicleLocation`, `fullName` y `email`. El canario del nombre sirve como canario del vehículo | `model/VehicleLocationResponse.java` |
| Login en la interfaz | Funcionó con `button[type="submit"]` y los placeholders `Email` y `Password`; llega a `/dashboard`. La sesión se guarda en `localStorage["persist:reducers"]` con un retraso: hay que esperar `isLoggedIn = true` antes de recargar | `containers/login/login.js`, `components/login/login.tsx`, `index.tsx`, `reducers/userReducer.ts` |
| Dashboard en el navegador | Al cargar pide solo `GET /identity/api/v2/vehicle/vehicles`; la ubicación solo al pulsar "Refresh Location" | `containers/dashboard/dashboard.js` |

## 4. Pendientes y límites encontrados

| # | Paso | Dónde | Bloquea el cierre |
|---|---|---|---|
| 1 | ~~Correr `probar_crapi.py` y `--grafo` con crAPI levantado~~ | Hecho el 18/11 | — |
| 2 | Fijar la versión de crAPI | `crAPI-main/deploy/docker/.env` | No, pero conviene |
| 3 | ~~Confirmar qué `mechanic_api` funciona~~ | Hecho: `localhost:8888` | — |
| 4 | ~~Corrida con crAPI en modo `reglas_llm` (Ollama abierto), para la hipótesis H3~~ | Hecho el 18/11 | — |
| 5 | Revisar la RAM con Juice Shop, crAPI, Ollama y Chromium a la vez | Este equipo | No |
| 6 | Actualizar el informe y `ARQUITECTURA.md` | Tú | Sí, para la entrega |

### Paso 1. Prueba con crAPI (hecho el 18/11)

- [x] crAPI levantado con `docker compose -f docker-compose.yml --compatibility up -d`.
- [x] `preparar_y_probar_crapi.bat`: `.venv` rehecho, `verificar_adaptadores.py` 12 `[OK]`, `probar_crapi.py` 4 `[OK]`.
- [x] `probar_crapi_grafo.bat`: 5 `[OK]` en la segunda corrida (ver sección 2).

### Paso 4. Corrida en modo `reglas_llm` (hecho el 18/11)

`probar_crapi_grafo_llm.bat`: 9 `[OK]`, 2 consultas a `gemma4:e4b` (ver sección 2). Si en otra corrida el LLM marcara un pendiente como identificador privado, sus hipótesis quedarían `dudoso` ("requiere_llm"), porque el oráculo determinista no puede confirmarlas.

### Paso 2. Versión de crAPI

`.env` trae `VERSION=latest`, así que `docker compose pull` baja la última versión publicada, no necesariamente la 1.1.5 que se revisó. Para fijarla, poner `VERSION=` con la etiqueta de la 1.1.5 que figure en Docker Hub para las imágenes `crapi/*`.

### Paso 3. `mechanic_api`

La interfaz envía como `mechanic_api` la URL del navegador (`http://localhost:8888/workshop/api/mechanic/receive_report`). Esa URL la llama el contenedor workshop, y dentro de Docker `localhost` es el propio contenedor. Si responde 400 ("Could not connect"), el adaptador reintenta con `http://crapi-web/workshop/api/mechanic/receive_report`, el nombre del servicio web en la red de Docker. Las dos son peticiones de preparación; ninguna prueba sale del alcance (RNF10). `probar_crapi.py` muestra cuál funcionó.

### Límites (documentar, no resolver)

- **Ubicación del vehículo (BOLA 1):** el dashboard no la pide al cargar; solo al pulsar "Refresh Location", y el Explorador no pulsa botones. Es esperable que no aparezca en la evidencia; `probar_crapi.py --grafo` lo informa.
- **BFLA (desafío 7, borrar un video ajeno):** es un DELETE. Queda fuera porque las pruebas son solo GET (RNF02).
- **Efecto de un GET en crAPI:** `GET /workshop/api/mechanic/mechanic_report` genera un PDF del reporte en el servidor (`service_report_pdf`). La prueba no cambia datos, pero conviene mencionarlo en el informe.
- **Cuentas que ya existían:** si A o B se registraron antes con un nombre sin canario, su vehículo queda sin canario y el oráculo usa el inventario. El reporte siempre lleva canario, porque se crea en cada ejecución.
- **Cada ejecución crea un reporte nuevo por cuenta,** igual que Juice Shop crea una dirección y una tarjeta nuevas.
- **Chatbot y chromadb** no se usan; si fallan al levantarse, no bloquean la prueba.
- **Ubicación del vehículo (BOLA 1), confirmado en la corrida:** 0 peticiones a `/location` en la evidencia.
- **Endpoints sin hipótesis:** `vehicles`, `orders/all`, `service_requests/null` y los demás listados se omitieron (`sin_datos_propios`: 5) porque sus respuestas no traen el canario ni el correo de la cuenta. `service_requests/null` es una llamada de la propia interfaz de crAPI con un VIN vacío.
- **`datos/20261117_162744/analisis_solo_reglas.json`** lo creó `verificar_analista_paso5.py` al correr la línea base (es su comportamiento normal). El `analisis.json` de esa carpeta quedó igual en contenido.

### Para el informe y `ARQUITECTURA.md`

- El Explorador ya no depende de Juice Shop: el alcance indica el adaptador (`"adaptador": "juice_shop"` o `"crapi"`), y `adaptadores.py` define su interfaz común.
- La sesión (`sesion.py`) lleva las cabeceras con que la aplicación la reconoce; la Validación las repite sin conocer la aplicación.
- crAPI agrega dos objetos sembrados: `vehiculo` (id en la ruta) y `reporte` (id en la consulta, `report_id`). El segundo prueba que el Analista asigna el dueño de un id de consulta con el inventario, sin LLM.
