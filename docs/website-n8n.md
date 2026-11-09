# Mosfix → OmniAgent → n8n → Ollama (validación local)

## Estado verificado el 2026-11-09

- Workflow existente: `WIoAgLGVugSezGQV`, **OmniAgent – Ingreso de mensajes | Website**, API pública local `http://127.0.0.1:5678`. Estaba activo al iniciar esta revisión y se conservó ese estado; no se creó ni activó otro workflow. El JSON exportado sigue con `active=false` para evitar activaciones accidentales al importarlo.
- Se corrigieron las referencias de los nodos **Preparar respuesta** y **Confirmar respuesta guardada** a `$('Validar mensaje recibido')`. Los seis nombres en español se preservaron. El PUT al workflow existente respondió 200 y su versión publicada coincidió con la guardada.
- Las credenciales referenciadas ya existen: webhook Header Auth `X-Webhook-Key` coincidente con `N8N_WEBHOOK_KEY`; callback Header Auth `X-Service-Key` coincidente con la API. Se comprobaron sin mostrar valores. `N8N_PUBLIC_API_KEY` solo se usa para administración local y no se incorpora al JSON ni al navegador.
- API y worker del contenedor coinciden con el código revisado. El callback recibe `conversation_id`, `inbound_message_id`, `respuesta` y conserva el `tenant_id` del evento como dato; la autorización del tenant procede exclusivamente de la credencial de servicio (`N8N_TENANT_ID=1`).
- El esquema físico de 018 existe y coincide con la base temporal migrada: columnas, defaults, identidad, nulabilidad, índices y restricciones. **El ledger local solo registra 001–016; no registra 017 ni 018.** No se ejecutaron migraciones ni se alteró el ledger. No volver a ejecutar 018 a ciegas: contiene CREATE/ALTER y el esquema ya existe. Hace falta reconciliar el historial con el administrador antes de habilitar el worker continuo.

## Direcciones Docker y Ollama

Ollama escucha actualmente solo en `172.18.0.1:11434`, la puerta de enlace real de `web_network`. Desde n8n funciona `http://172.18.0.1:11434/api/tags` (200); **`host.docker.internal` resuelve a otra dirección y falla**. Por eso `Generar respuesta con IA` conserva la URL comprobada `http://172.18.0.1:11434/api/chat`, modelo `qwen2.5:3b`, `stream=false`, mensajes system/user, timeout 25 segundos. Si cambia la subred Docker, actualizar esa URL o corregir el alias y verificarlo antes de usarlo. No se reinició n8n para alterar las redes de otros canales.

`ss` confirma que Ollama ya no escucha en todas las interfaces. No hay listener en las direcciones Wi-Fi/Tailscale con esta configuración. No se certifica desde aquí la ausencia de rutas o reglas NAT externas hacia la IP del bridge; verificar firewall/rutas si se requiere aislamiento de otros contenedores o redes enrutadas. No publicar 11434 ni usar `0.0.0.0`. El modelo no requiere clave OpenAI.

El prompt de Mosfix responde en español, solicita datos útiles y remite a atención humana para condiciones comerciales y dudas técnicas. No debe inventar precios, horarios, garantías, diagnósticos ni cobertura; tampoco promete que un agente haya sido notificado. El texto del visitante se envía como mensaje user separado del system prompt. El modelo puede incumplir instrucciones y no constituye una fuente de condiciones comerciales verificadas.

## Persistencia y seguridad

El navegador utiliza exclusivamente `/api/v1/widget/*`, nunca n8n u Ollama. El backend valida origen exacto, sitio activo y sesión de visitante. Mensaje y evento outbox se guardan en la misma transacción; el reintento idempotente no crea otro evento. Las conversaciones cerradas rechazan nuevos mensajes; con intervención humana se guardan mensajes sin automatizarlos.

El worker verifica canal, sitio, tenant, conversación abierta y automatización; reserva con `FOR UPDATE SKIP LOCKED`, token UUID y lease de 300 segundos, y cierra la transacción antes del HTTP (timeout 30 segundos). Los errores programan backoff exponencial hasta 300 segundos. Un HTTP 200 no basta: exige un outbound persistido para el mismo `inbound_message_id`, conversación y tenant. El callback revalida autorización, reutiliza `message_service.py` y la unicidad existente evita respuestas duplicadas. Un reintento puede duplicar una llamada al modelo, pero no la respuesta persistida.

El payload incluye solo `tenant_id`, `site_id`, `conversation_id`, `inbound_message_id`, `mensaje` y `canal=website`; no contiene tokens de visitante ni credenciales. El workflow conserva autenticación de webhook/callback y no guarda ejecuciones exitosas, fallidas ni manuales según sus settings.

## Mosfix y prueba aislada reproducible

Las seis inclusiones actuales del sitio usan la API `https://omniagent-api.jaimeberrios.com` y el public_id registrado de Mosfix. Su origen registrado es `https://mosfix.jaimeberrios.com`. No se modificó esa configuración ni se enviaron solicitudes de prueba al hostname público de la API.

`backend/scripts/test_website_local.cjs` lee el widget real del repositorio hermano, registra un sitio **Mosfix LOCAL E2E** en el mismo tenant con origen loopback HTTPS y crea una conversación nueva. Sirve solo una página de prueba interceptada por Playwright y llama realmente a la API en `127.0.0.1:8000`. Concede permiso de red local de Chromium únicamente al origen de prueba; no deshabilita CORS. El script verifica preflight permitido/rechazado, sesión, envío, evento pendiente, procesamiento dirigido exclusivamente a ese evento, respuesta persistida y visible, y renovación sin cambiar conversación. No arranca un worker continuo ni procesa eventos ajenos. Al terminar desactiva el sitio de prueba, cierra la conversación y revoca sesiones; conserva los registros para auditoría. Requiere que el workflow ya esté activo y coincida con el JSON revisado.

```sh
cd /home/jaimeberrios/Proyectos/OmniAgent
npm install --prefix /tmp/omni-browser-check playwright --no-audit --no-fund
PLAYWRIGHT_MODULE=/tmp/omni-browser-check/node_modules/playwright \
CHROMIUM_PATH=/usr/bin/chromium \
node backend/scripts/test_website_local.cjs
```

Resultado real: **PASS**, conversación 16, evento 1, un único outbound. El widget mostró la respuesta de Ollama; CORS y renovación pasaron. No se usaron respuestas simuladas en este recorrido. Las primeras pruebas del navegador no completaron la sesión por el permiso de acceso a loopback de Chromium; se corrigió la configuración del arnés de prueba, sin relajar la API ni modificar el widget.

Pruebas de Website sobre el PostgreSQL **temporal existente** (sin aplicar migraciones):

```sh
# Si está detenido, iniciar SOLO el cluster temporal ya preparado:
/usr/lib/postgresql/18/bin/pg_ctl -D /tmp/omni-website-pg \
  -l /tmp/omni-website-pg.log \
  -o '-k /tmp/omni-website-socket -p 55439 -h 127.0.0.1' start
PYTHONPATH=backend \
OMNI_TEST_DATABASE_URL=postgresql+psycopg://jaimeberrios@127.0.0.1:55439/omni_test \
.venv/bin/python -m pytest backend/tests/test_website_workflow.py backend/tests/test_website_integration.py -q -rs
/usr/lib/postgresql/18/bin/pg_ctl -D /tmp/omni-website-pg stop
```

Resultado: **19 aprobadas, ninguna omitida ni fallida**. Además, la suite backend completa con `-k 'not migration'` produjo **48 aprobadas y 2 excluidas explícitamente** para no ejecutar migraciones; ninguna fallida. Sin `OMNI_TEST_DATABASE_URL`, las 11 de integración se omiten; no cuentan como aprobadas. La advertencia Starlette/httpx es de deprecación. No ejecutar estos tests sobre la base persistente: preparan y modifican colas de prueba.

Pruebas del widget:

```sh
cd /home/jaimeberrios/Proyectos/mosfix
PLAYWRIGHT_MODULE=/tmp/omni-browser-check/node_modules/playwright \
CHROMIUM_PATH=/usr/bin/chromium node --test tests/widget.test.cjs
```

Resultado: **17 aprobadas, 1 omitida** (prueba antigua de operador sin fixture), ninguna fallida. La E2E real anterior se ejecutó por separado y no es esa prueba omitida. Se validan renderizado como texto, polling, recuperación de envíos inciertos, UUID idempotente, renovación y vistas de 390/768/1440 px. El widget no presentó un defecto que requiriera cambiar su código.

## Worker local preparado, todavía detenido

`infrastructure/compose.website-local.yaml` permite habilitar únicamente el servicio website con `WEBSITE_WORKER_ENABLED=true`; la combinación de Compose se validó sin iniciar servicios. El servicio conserva el perfil optativo `website`, `restart=no`, red interna y `web_network`, webhook `http://n8n:5678/webhook/omniagent-website` y la clave del entorno. **No se arrancó debido al ledger de migraciones pendiente de reconciliar.**

Después de resolver ese bloqueo y revisar la cola website pendiente, el comando exacto para iniciar solo este servicio, sin recrear dependencias ni afectar otros canales, es:

```sh
cd /home/jaimeberrios/Proyectos/OmniAgent
docker compose --env-file infrastructure/.env \
  -f infrastructure/compose.yaml -f infrastructure/compose.local.yaml \
  -f infrastructure/compose.website-local.yaml --profile website \
  up -d --no-deps website-worker
```

No se modificaron workflows de Messenger, WhatsApp o Instagram, no se eliminaron contenedores ni se hizo commit, push o despliegue.
