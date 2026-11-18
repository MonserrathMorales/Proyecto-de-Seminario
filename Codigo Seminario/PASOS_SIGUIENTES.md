# Pasos siguientes para terminar el prototipo del Seminario

Actualizada el 16 de noviembre de 2026, después de probar el orquestador con los tres agentes.

## Tu siguiente acción

**Llevar la carpeta `prototipo` al equipo de la RTX 3050 y hacer la corrida real contra Juice Shop** (pasos 1 a 4). Es lo único que falta para cumplir el criterio de término del Seminario. Todo lo que se podía probar sin el laboratorio ya está probado.

**Criterio de término** (sección 8.4 del informe): el flujo confirma al menos un desafío de lectura de Juice Shop, con datos canario o con el inventario, sin intervención manual entre etapas.

## Qué ya está hecho

| Qué | Cómo se comprobó | Estado |
|---|---|---|
| Explorador | Corrida contra Juice Shop el 13 y 14 de noviembre | Listo |
| Analista | Corrida contra Juice Shop el 14 de noviembre | Listo |
| Agente de Validación y Remediación | `verificar_validacion.py`: 14 criterios con una aplicación simulada | Lógica probada |
| Orquestador con los tres agentes | `verificar_orquestador.py`: 11 criterios con el grafo real de LangGraph, Explorador y aplicación simulados | Unión probada |
| Correcciones de la revisión | Pasos 1, 2, 3 y 5 del Analista siguen en `[OK]` | Listo |
| Diagrama y documento de arquitectura | `arquitectura/` | Actualizados |

## Qué falta

| # | Paso | Dónde | Bloquea el cierre |
|---|---|---|---|
| 1 | Llevar el código al equipo de la RTX 3050 | Ambos equipos | Sí |
| 2 | Verificaciones sin servicios | RTX 3050 | Sí |
| 3 | Preparar el laboratorio | RTX 3050 | Sí |
| 4 | **Corrida real del flujo completo** | RTX 3050 | **Sí** |
| 5 | Evidencia de que el Analista consulta al modelo | RTX 3050 | No, pero conviene |
| 6 | Decidir qué hacer con el LLM en la corrida integrada | Tú | No |
| 7 | Cerrar los pendientes de código | Con Claude | No |
| 8 | Actualizar el informe | Tú, con ayuda de Claude | Sí, para la entrega |

---

## Paso 1. Llevar el código al equipo de la RTX 3050

- [ ] En el equipo de la RTX 3050, guardar una copia de la carpeta `prototipo` que hay allá antes de sobrescribirla.
- [ ] Copiar desde este equipo la carpeta `Seminario/prototipo` completa, **sin** `.venv` ni `__pycache__`. El `.venv` no sirve en otro equipo.
- [ ] Copiar también `Seminario/arquitectura` y este archivo.

Archivos nuevos o modificados respecto de la versión que tienes allá:

| Archivo | Cambio |
|---|---|
| `prototipo/cruce.py`, `oraculo.py`, `remediacion.py`, `validacion.py` | Nuevos: el agente de Validación y Remediación |
| `prototipo/modelos.py` | Modelos nuevos y fechas de vigencia en el alcance |
| `prototipo/grafo.py` | Nodo `validacion` |
| `prototipo/hipotesis.py`, `extraccion.py`, `captura.py` | Correcciones de la revisión |
| `prototipo/juice_shop.py` | Función `cabeceras()` |
| `prototipo/explorador.py`, `clasificador.py` | Cambios de una línea |
| `verificar_validacion.py`, `verificar_orquestador.py`, `simulacion.py` | Nuevos |
| `verificar_analista_paso1.py`, `verificar_analista_paso5.py`, `demo_explorador.py` | Ajustes menores |

`Seminario/prototipo_respaldo_20261116.zip` contiene la versión **anterior** a estos cambios, por si hay que volver atrás.

## Paso 2. Verificaciones sin servicios

Confirman que la copia quedó bien antes de levantar Juice Shop. No necesitan Docker ni Ollama. En este equipo ya pasaron todas; allá deben dar lo mismo.

Según el `.venv` de `prueba_concepto`, en ese equipo el proyecto está en `C:\seminario`. Ajusta la ruta si no es así.

```powershell
cd C:\seminario\prototipo
C:\seminario\prueba_concepto\.venv\Scripts\Activate.ps1
python verificar_analista_paso1.py
python verificar_analista_paso2.py
python verificar_analista_paso3.py
python verificar_validacion.py
python verificar_orquestador.py
```

- [ ] Todas las líneas dicen `[OK]`.
- [ ] `verificar_validacion.py` muestra 14 criterios en `[OK]`.
- [ ] `verificar_orquestador.py` muestra 11 criterios en `[OK]`.

Ninguno de estos scripts modifica `datos/`: los dos últimos trabajan en carpetas temporales.

**Si algo falla aquí**, no sigas: pégale a Claude la salida completa.

## Paso 3. Preparar el laboratorio

- [ ] Reiniciar el contenedor de Juice Shop, para partir de una base de datos limpia. Los identificadores de las cuentas y canastas dependen de eso.
- [ ] Comprobar que responde en `http://localhost:3000`.
- [ ] Comprobar que el puerto 8080 está libre (que no quedó un `mitmdump` abierto de una corrida anterior).
- [ ] Abrir Ollama. Con la evidencia actual el modelo no se consulta, pero si aparece un candidato fuera del inventario el Analista lo va a necesitar.
- [ ] Agregar a `alcance_juice.json` las fechas de la autorización del laboratorio (RF01). Hoy no las tiene, así que no hay límite de fechas:

```json
"vigencia_desde": "2026-11-01",
"vigencia_hasta": "2026-12-31",
"autorizado_por": "Laboratorio local del Seminario"
```

Las fechas del ejemplo son un supuesto: pon las de tu autorización real.

## Paso 4. Corrida real del flujo completo

Es el paso que cierra el Seminario. Es la primera vez que el agente de Validación y Remediación le habla a Juice Shop de verdad, y la primera vez que el grafo de tres agentes corre con el navegador y el proxy.

```powershell
python verificar_validacion.py --completo
```

Se abre el navegador tres veces (A, B y sin sesión) y tarda cerca de dos minutos.

- [ ] La Parte 2 muestra las etapas `explorador`, `analista`, `validacion` y `cerrar` con resultado `ok`.
- [ ] Hay al menos un veredicto `confirmado`.
- [ ] Los 6 criterios de la Parte 2 dicen `[OK]`.
- [ ] Guardar la salida completa de la consola en un archivo de texto junto a la evidencia.
- [ ] Pegarle la salida a Claude, salga bien o mal.

### Qué resultado se espera

| Hipótesis | Resultado esperado | Por qué |
|---|---|---|
| Canasta de A pedida por B, y de B pedida por A | `confirmado` | Es el desafío documentado de Juice Shop |
| Dirección de A pedida por B, y viceversa | Por observar | Muestra si la aplicación protege el objeto. Si sale `confirmado` por canario, es una fuga real |
| Cualquier objeto pedido sin sesión | `descartado` por `acceso_denegado` | Se espera que Juice Shop exija autenticación en esos endpoints |
| `whoami` sin sesión | `descartado` o `dudoso` | Ver la tabla siguiente |

### Cómo leer los resultados inesperados

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| Todo `dudoso` con `linea_base_invalida` | El dueño no pudo leer su propio objeto: el token no fue aceptado | Pegar la salida a Claude; hay que revisar `cabeceras()` en `juice_shop.py` |
| `dudoso` con `linea_base_sin_marca` en `whoami` | Juice Shop no reconoció la sesión en ese endpoint | No es un falso positivo. Pegar la salida para ajustar el adaptador |
| `dudoso` con `error_de_red` | Tiempo de espera o Juice Shop caído | Reiniciar el contenedor y repetir |
| El flujo termina con `error` en una etapa | La etapa falló y el grafo cerró ordenadamente | Abrir `datos/<ejecucion>/registro.json` y pegar el error |
| Ningún `confirmado` | El criterio de término no se cumple | Pegar la salida completa y el `validacion.json` |

**Qué enviarle a Claude:** la salida completa de la consola. No imprime tokens ni claves. Si además adjuntas `validacion.json`, viene ya con los secretos ocultos.

## Paso 5. Evidencia de que el Analista consulta al modelo

En la corrida integrada el modelo no se usa (0 consultas). La única prueba de que el Analista se conecta con Gemma 4 E4B es este script, que usa los 23 casos etiquetados. Necesita Ollama abierto.

```powershell
python verificar_analista_paso4.py
```

- [ ] Todos los criterios dicen `[OK]`.
- [ ] Guardar la salida: tiempos por consulta, estabilidad entre repeticiones y la comparación de "solo reglas" con "reglas + LLM". Son datos para la sección 8.4.

## Paso 6. Decidir qué hacer con el LLM en la corrida integrada

Con las pantallas actuales, los 4 candidatos de Juice Shop se resuelven con el inventario y el modelo nunca se consulta. En la defensa pueden preguntar dónde interviene la IA. Hay dos caminos:

| Opción | Qué implica |
|---|---|
| **A. Ampliar las pantallas del alcance** | Agregar a `alcance_juice.json` una pantalla que pida un objeto que el sistema no sembró. Así el modo `reglas_llm` se ejercita en la corrida real. Requiere repetir el paso 4 |
| **B. Declararlo como resultado** | Escribir en el informe que el inventario resolvió todos los candidatos y que el LLM se midió aparte (paso 5). No requiere más código |

La opción B es suficiente para el Seminario y es coherente con el principio de que el LLM solo interviene en los casos ambiguos. La opción A da una demostración más convincente.

## Paso 7. Cerrar los pendientes de código

Ninguno bloquea la corrida real. Se pueden pedir a Claude en cualquier momento, incluso mientras haces los pasos 1 a 4.

- [ ] `entorno.json` por ejecución: equipo, versiones de paquetes, modelo, su digest y opciones (RNF04).
- [ ] `requirements.txt` propio en `prototipo`, con las versiones del Anexo D.
- [ ] Ocultar secretos también en cuerpos de formulario y en la consulta de la URL (RNF06).
- [ ] No consultar al modelo los candidatos de peticiones que no son GET, porque después se omiten.
- [ ] Opcional: poner el proyecto bajo control de versiones con `git init`, excluyendo `.venv`, `__pycache__` y los archivos `.mitm`.

## Paso 8. Actualizar el informe

Conviene hacerlo después del paso 4, para escribir con los resultados reales. El informe v9 quedó desalineado con el código en estos puntos:

- [ ] **Sección 6.2 y Tabla 6.1.** Hablan de Ejecutor y Juez por separado, y de "tres agentes con LLM y tres componentes deterministas". El código tiene tres agentes: Explorador, Analista, y Validación y Remediación. La tabla de nombres antiguos y actuales está en la sección 1 de `arquitectura/ARQUITECTURA.md`.
- [ ] **Figura de la arquitectura.** Se puede usar `arquitectura/arquitectura.png`.
- [ ] **Sección 8.4.** Dice que el Analista es "el siguiente componente en construcción". Hay que describir el Analista y el agente de Validación y Remediación, y agregar una tabla con los resultados del paso 4: hipótesis, peticiones enviadas, confirmados, descartados y dudosos.
- [ ] **Correcciones surgidas de la implementación.** Vale la pena contarlas, porque son hallazgos propios: la marca del dueño no puede buscarse como texto (el id `26` aparece dentro de `2026`), y el cruce debe calcularse desde el dueño del objeto y no desde la sesión.
- [ ] **Anexo A.** RF01 ya contempla las fechas; RF08 queda parcialmente cubierto con la corrección sugerida por plantilla.
- [ ] **Sección 7.4 y Tabla 7.1.** Cambiar "Explorador, Analista y Ejecutor" por los nombres actuales.
- [ ] **Sección 9.** Actualizar las conclusiones con el resultado de la corrida real.
- [ ] **Remediación.** El agente clasifica con CWE-639 y CWE-306; hay que citar el catálogo CWE de MITRE en APA 7 y agregarlo a las referencias.

## Qué no hacer

- No correr el flujo contra nada que no sea el laboratorio local. El código solo acepta la URL de `alcance_juice.json`, y debe seguir así.
- No subir a ningún repositorio público los archivos `.mitm` de `prueba_concepto`: son capturas sin filtrar y pueden contener claves y tokens de las cuentas de prueba.
- No dar por terminado el prototipo antes del paso 4: hasta entonces, el tercer agente y el grafo completo solo están probados con una aplicación simulada.
