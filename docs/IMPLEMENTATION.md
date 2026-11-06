# Modernización de OmniAgent

Base verificada: rama `feature/website-chat`, commit `d77f36b`, árbol inicialmente limpio. Se continuó la aplicación existente. No hubo commits, push, acceso a VPS ni cambios de producción. La memoria previa solo se usó para localizar contratos; el alcance anterior limitado al frontend fue sustituido por la autorización actual. No se encontró un archivo de auditoría anterior en este checkout; los cambios se basaron en hallazgos comprobados en el código.

## Cambios técnicos

- `message_service.py` concentra la persistencia transaccional de respuestas y su outbox. Vue encola WhatsApp y Messenger; website hace disponible la respuesta al polling. No se hace una llamada de red dentro de la transacción. Los workers existentes permanecen.
- La clave de idempotencia del operador tiene unicidad por organización/conversación. Un bloqueo de conversación serializa reintentos concurrentes. El frontend conserva la clave después de un error de red. n8n conserva `meta_message_id` e `inbound_message_id` en el workflow exportado; la respuesta automática no se puede registrar sin el ID entrante. Esta validación adicional requiere actualizar el workflow y cualquier otro consumidor interno al mismo tiempo.
- Recuperación de WhatsApp según `claimed_at`, propiedad por UUID y descarte de finalizaciones obsoletas. Los envíos inciertos quedan `unknown` y no vuelven automáticamente a `pending`. Messenger captura errores inesperados y supervisa su ciclo. Compose reinicia workers ante fallos; los workers desactivados permanecen inactivos sin salir repetidamente.
- `sent` significa aceptación del proveedor con ID, no recepción ni lectura por el cliente. No se implementaron nuevos recibos de entrega de Meta.
- Webhooks: firmas existentes conservadas, validación de estructura/JSON, límite de cuerpo de 1 MiB, contenido de hasta 4096 caracteres. Login, envío de operadores (60/minuto por miembro/organización) y widget tienen rate limiting compartido en PostgreSQL. No se añadió Redis.
- Bandeja: consulta conjunta del último mensaje, paginación por ID, búsqueda de cliente y filtros por canal, estado y asignación. Historial y clientes también paginados. El adaptador Vue consume todas las páginas para conservar la búsqueda local existente. La búsqueda del servidor está disponible para una futura carga progresiva de listas grandes.
- Nuevos routers `widget.py` y `operations.py`; el resto de endpoints mantiene su ubicación. El historial no mezcla notas con mensajes externos.
- Asignación validada por membresía, guardas de base de datos, estado de intervención humana, marca de lectura compartida por equipo y eventos con actor. Propietario administra roles `admin`/`agent` de miembros existentes; no puede degradar al propietario. Agentes solo pueden tomar conversaciones sin asignar o propias.
- Sitios por organización con identificadores públicos, orígenes exactos, tokens de visitante en hash, expiración/rotación/revocación y aislamiento de conversación. La desactivación de un sitio bloquea sus visitantes. Ver [MOSFIX_WIDGET.md](MOSFIX_WIDGET.md).
- Auditoría de respuestas, estados, asignaciones, notas, intervención, cambios de rol y altas/desactivaciones de sitio. La auditoría de control de n8n se conserva.

## Pantallas

| Pantalla | Cambios |
|---|---|
| Login | Descubrimiento de organizaciones por membresía, selección cuando hay varias; JWT sigue en memoria |
| Dashboard | Canal website, respuestas registradas diferenciadas de entregas, resumen de pendientes y sin asignar |
| Conversaciones | Polling de 5 s, aviso independiente de sincronización, borradores por conversación, UUID conservado en reintentos, estados por canal, no leídos, asignadas a mí, notas, asignación y control humano |
| Clientes | Identidad del visitante web y columna de canales asociados; vínculos al historial conservados |
| Automatizaciones | Conserva telemetría/control real y roles existentes; el workflow exportado propaga IDs y requiere autenticación de encabezado |
| Configuración | Miembros y cambios de rol existentes; alta/listado/desactivación de sitios; preferencias de tema conservadas |
| Layout y sistema visual | Identidad azul petróleo/verde conservada, tokens semánticos, contraste de texto/avatares/canales, tamaños de interacción, indicador de no leídos, navegación responsive y nombre de organización |

No se afirma una certificación WCAG. Las verificaciones automáticas no sustituyen lector de pantalla, teclado completo, zoom ni evaluación manual de todos los estados.

## Migraciones y ejecución

| Migración | Contenido | Condiciones |
|---|---|---|
| 014 | Clave de mensaje, sitios, sesiones y límites de solicitudes | Ejecutar antes del nuevo código; índices/tabla nueva y unicidad nullable |
| 015 | Asignación, lectura, intervención, eventos de conversación y auditoría administrativa | Esquema 014 aplicado |
| 016 | Envios heredados sin claim a unknown, FK de asignación y índice del cursor | Esquema 015; revisar entregas unknown después |

Aplicadas exclusivamente al contenedor temporal `omniagent-test-website`, base `omni_test`, puerto 55439, almacenamiento tmpfs. El migrador utiliza un advisory lock de PostgreSQL para impedir dos ejecuciones simultáneas, una transacción por archivo y registro de versiones. Una segunda ejecución omite versiones aplicadas. No modifica los archivos 001–013.

El arranque de API ya no ejecuta migraciones de forma implícita: `RUN_MIGRATIONS=false` por defecto. Para una base existente hace falta autorización operativa, respaldo y ventana de despliegue. Este trabajo no autoriza su ejecución en producción. Las nuevas FKs/índices pueden bloquear tablas mientras se crean; evaluar volumen y ventana antes de aplicarlas. No se suministra rollback destructivo.

API y workers usan `omniagent-backend:${APP_VERSION:-dev}`. Construir una vez desde `backend/Dockerfile` y usar un tag inmutable para la versión que se despliegue; `APP_VERSION` identifica la versión en API y logs. No se construyeron ni desplegaron las imágenes productivas. Los Dockerfiles `*-local` heredados no son necesarios en el Compose actualizado.

## Variables nuevas

- `APP_VERSION`: tag común de imagen y versión visible/logueada; por defecto `dev`.
- `RUN_MIGRATIONS`: habilitación explícita de migraciones al arrancar API; por defecto `false`.
- `MIGRATIONS_DIR`: directorio opcional para el migrador; el valor predeterminado se resuelve desde el script.
- `N8N_WEBHOOK_KEY`: secreto del encabezado `X-Webhook-Key` que usa el worker entrante de WhatsApp. Configurar en n8n una credencial Header Auth con el mismo encabezado/valor; asociarla al nodo Webhook del workflow importado. Las credenciales de los nodos HTTP siguen usando `X-Service-Key`/`N8N_API_KEY`. No son la misma credencial.
- `N8N_WEBHOOK_URL`: URL interna opcional para el worker; por defecto `http://n8n:5678/webhook/omniagent-mensajes`. No confundir con `WEBHOOK_URL` de n8n, que describe su dirección pública.
- `OMNI_TEST_DATABASE_URL`: solo pruebas; exige una base desechable llamada `omni_test`.
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`: opcional, usa Chromium ya instalado para pruebas.

Los flags existentes `MESSENGER_OUTBOUND_ENABLED` y `WHATSAPP_OUTBOUND_ENABLED` siguen desactivados por defecto. El override local dejó de activar Messenger automáticamente. El worker saliente WhatsApp ahora recibe su token existente y una red con salida externa. No se activaron envíos reales.

## Validación local reproducible

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
# En otra terminal, desde frontend:
npm ci
npm run build
npm test
# Si Chromium no está instalado: npx playwright install chromium
```

Para pruebas SQL, crear SOLO un contenedor nuevo sin volumen persistente. El password de ejemplo es exclusivo de pruebas locales:

```sh
docker run --rm -d --name omniagent-test-website --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=disposable-test-only -e POSTGRES_DB=omni_test \
  -p 127.0.0.1:55439:5432 postgres:17-alpine
export DATABASE_URL=postgresql+psycopg://postgres:disposable-test-only@127.0.0.1:55439/omni_test
.venv/bin/python backend/scripts/migrate.py
OMNI_TEST_DATABASE_URL="$DATABASE_URL" PYTHONPATH=backend .venv/bin/pytest -q backend/tests
# Al terminar, destruir exclusivamente ese contenedor temporal:
docker stop omniagent-test-website
```

Nunca sustituir esa URL por una base persistente para ejecutar la suite: las pruebas escriben y actualizan registros. Sin `OMNI_TEST_DATABASE_URL`, las pruebas de integración se omiten; las de contrato/unidad no requieren PostgreSQL. En entornos que bloquean hilos/red local se necesita ejecutar fuera de esa restricción.

## Límites y trabajo dependiente

- Mosfix independiente: pendiente conexión de su widget real, HTTPS público y validación de ambos lados. No se accedió a su repositorio ni a Caddy.
- Messenger/WhatsApp: sin pruebas externas ni validación de tokens, permisos, ventanas o entrega real; los tests de sender existentes usan mocks. Website no necesita proveedor externo.
- Conexiones de Meta siguen configuradas en servidor: WhatsApp es una conexión por instancia/tenant configurado; Messenger tiene páginas por tenant con token de servidor existente. Un gestor completo de secretos/conexiones Meta por organización necesita diseño de almacenamiento cifrado/provisión y queda pendiente; no se presenta una pantalla ficticia.
- Alta/invitación/retiro de miembros y recuperación de contraseñas no se implementaron. Los roles existentes sí se pueden gestionar con autorización real.
- Los indicadores de lectura son compartidos por el equipo, no preferencias de lectura individuales. El estado pendiente se deriva del último mensaje y del estado abierto; no calcula SLA.
- `GET` de historial del widget excluye notas porque se almacenan en otra tabla. El historial de eventos del equipo entrega hasta 100 por página; el endpoint admite `after_id`.
- La intervención humana bloquea creación de nuevas respuestas desde el endpoint interno; no cancela automáticamente respuestas que ya estaban encoladas. n8n debe tratar 409 como intervención/conflicto y evitar reintentos indefinidos. No se ha importado el workflow en una instancia real.
- Consumidores antiguos que omitan IDs no pueden garantizar idempotencia. El endpoint interno saliente ahora rechaza la ausencia de `inbound_message_id`; actualizar el export y consumidores en el mismo despliegue. El interno entrante conserva el campo opcional por compatibilidad, pero el workflow exportado siempre lo propaga. La API de operadores conserva el campo de clave opcional por compatibilidad; Vue siempre lo envía.
- Limpieza operativa: planificar eliminación de ventanas viejas en `request_limits` y sesiones expiradas/revocadas según retención. No se ejecutó limpieza en bases persistentes. El rate limit por IP necesita configuración correcta de proxies confiables; no proporciona por sí solo protección distribuida contra bots.
- No se implementó facturación, marketplace, Redis ni microservicios.

## Prueba integrada de navegador sin mocks

Con el PostgreSQL desechable anterior en ejecución, desde la raíz:

```sh
export DATABASE_URL=postgresql+psycopg://postgres:disposable-test-only@127.0.0.1:55439/omni_test
export OMNI_TEST_DATABASE_URL="$DATABASE_URL"
export JWT_SECRET_KEY=local-tests-only-key-at-least-32-characters
PYTHONPATH=backend .venv/bin/python backend/scripts/seed_test_browser.py
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8019
```

En otra terminal, dentro de `frontend`:

```sh
OMNI_BROWSER_FIXTURE=/tmp/omni-browser-fixture.json \
API_PROXY_TARGET=http://127.0.0.1:8019 npm test
```

El seed crea credenciales aleatorias exclusivas de pruebas en un archivo local con permiso 0600. La prueba usa la API real para crear el visitante y enviar su consulta; inicia sesión en Vue, responde como operador y recupera la respuesta con el token del visitante. Se ejecuta en los tres tamaños. `OMNI_BROWSER_FIXTURE` es solo de pruebas. Sin esta variable, los tres casos integrados se omiten de forma explícita. El JWT de operadores en memoria exige navegación SPA; recargar requiere volver a iniciar sesión.

## Evidencia de validación

- Backend: 31 pruebas aprobadas con PostgreSQL 17 temporal. Incluye contratos, autorización, aislamiento, firmas inválidas, idempotencia concurrente, recuperación por lease, propiedad obsoleta, rollback, sesiones expiradas/revocadas, límites compartidos, propagación de IDs y migraciones desde esquema vacío.
- Migraciones: 001–016 aplicadas en esquema temporal nuevo; segunda ejecución sin duplicación; edición de una migración aplicada rechazada por checksum; fallo de SQL revierte esquema y registro. Para versiones históricas sin checksum, la primera ejecución registra el checksum del archivo disponible como línea base, sin probar retrospectivamente qué archivo se ejecutó.
- Frontend: 12 pruebas de navegador aprobadas en 390/768/1440 px, incluidas tres con Vue/FastAPI/PostgreSQL reales. Las otras prueban demo sin llamadas, selección de organización con contratos simulados, borradores, respuesta idempotente, notas y axe en login y cinco pantallas con ambos temas.
- `npm run build` y comprobación TypeScript aprobados; Compose base + override validados con valores ficticios y `config --quiet`; Python compilado; `git diff --check` sin errores.
- Hubo fallos intermedios corregidos: test heredado que contaba columnas equivocadas, errores de sintaxis durante implementación, selector accesible ambiguo, sincronización/nombre de enlaces en pruebas, contrastes y navegación de test que recargaba el JWT en memoria. No quedan fallos conocidos en las suites ejecutadas al cierre.
- Aviso de la herramienta: Starlette depreca el adaptador de `httpx` del TestClient; la suite aprueba con `httpx` 0.28.1. No se cambió de cliente automáticamente. Playwright también emitió avisos de variables de color del terminal, sin afectar los resultados.
- La validación completa local del canal web no es una prueba del repositorio Mosfix ni de proveedores externos. No se ejecutó n8n real ni se construyeron todas las imágenes Docker.

Al cierre se detuvieron las dos ejecuciones temporales de FastAPI, se detuvo/eliminó el contenedor PostgreSQL desechable (`--rm`) y se retiró el archivo temporal de credenciales del navegador. Permanecen el código, el entorno virtual local, node_modules, dist y capturas de pruebas ignoradas por Git. Ver el inventario completo en [CHANGED_FILES.md](CHANGED_FILES.md).
