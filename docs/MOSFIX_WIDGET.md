# Contrato del widget de Mosfix

Implementación local de OmniAgent. El repositorio de Mosfix no se modificó y la conexión real entre ambos sitios queda por verificar.

## Preparación

1. Aplicar las migraciones 014–016 mediante un procedimiento autorizado. No arrancar código nuevo sobre el esquema anterior.
2. Como propietario o administrador, registrar el sitio en Configuración → Sitios web con nombre `Mosfix` y origen exacto `https://mosfix.jaimeberrios.com`, sin barra final. Alternativamente, `POST /tenants/{tenant_id}/websites` con JWT de operador y JSON `{"name":"Mosfix","origin":"https://mosfix.jaimeberrios.com"}`. El ID numérico es administrativo; usar `public_id` en el widget. No es un secreto.
3. Configurar en Mosfix el host HTTPS público de OmniAgent y ese `public_id`. No colocar JWT de operadores ni claves n8n en Mosfix.
4. El proxy debe preservar `/api/v1/widget/*`. El Nginx del frontend ya tiene una ubicación específica que conserva esa ruta. Los otros endpoints administrativos siguen detrás de `/api/`, que elimina ese prefijo antes de llegar a FastAPI. Si se accede directamente a FastAPI, usar las rutas documentadas sin ese prefijo administrativo.
5. El navegador envía `Origin`. Debe coincidir exactamente con el sitio registrado. Preflight admite `Authorization` y `Content-Type`; no usa cookies ni `credentials: include`. La lista CORS es dinámica por sitio. CORS por sí solo no autentica visitantes.

## Endpoints públicos

| Método y ruta | Entrada | Resultado |
|---|---|---|
| `POST /api/v1/widget/session` | `{"site_id":"PUBLIC_ID"}` | 201: `token`, `conversation_id`, `expires_at` |
| `POST /api/v1/widget/session/renew` | Bearer de visitante | 200: mismo contrato; rota el token y conserva conversación |
| `DELETE /api/v1/widget/session` | Bearer de visitante | 204; revocación inmediata |
| `POST /api/v1/widget/conversations/{id}/messages` | Bearer; `{"content":"Hola","idempotency_key":"UUID"}` | 201: mensaje persistido; un reintento devuelve el mismo ID |
| `GET /api/v1/widget/conversations/{id}/messages?after_id=0&limit=50` | Bearer | `messages`, `next_after_id`, `has_more` |

Un mensaje contiene `id`, `tenant_id`, `conversation_id`, `direction` (`inbound` del visitante u `outbound` del operador), `content`, `created_at` y campos opcionales del contrato común. El widget solo necesita los primeros campos de presentación; no debe interpretar persistencia como entrega externa.

- Token aleatorio de 256 bits; únicamente SHA-256 se almacena en PostgreSQL. Vigencia de 24 horas desde creación/renovación. Renovar antes del vencimiento y reemplazar el token anterior. Una sesión expirada no se recupera por identificador público; crear otra sesión inicia una conversación nueva.
- El token solo autoriza su conversación, organización y sitio. Desactivar el sitio bloquea las sesiones existentes. No hay endpoint para cambiar la conversación de una sesión.
- Contenido: 1–4096 caracteres, con al menos un carácter no blanco. Clave: 1–92 caracteres; conservar la misma clave y el mismo contenido durante todos los reintentos de una acción. Cambiar contenido con la misma clave produce 409.
- Historial: IDs ascendentes; `after_id >= 0`; `limit` de 1 a 100. Consumir páginas mientras `has_more` sea verdadero. Después consultar cada 5 segundos usando el último cursor. Deduplicar por ID, pausar cuando la pestaña está oculta y aplicar espera creciente ante fallos.
- 401: token expirado/revocado/inválido. 403: origen no permitido. 404: sitio o conversación inaccesible. 409: conflicto de clave o conversación cerrada. 413: cuerpo superior a 1 MiB. 422: validación. 429: esperar según `Retry-After` (60 s).
- Límites compartidos entre procesos de API: 10 sesiones por sitio/IP/minuto, 120 operaciones por sesión/minuto y 30 mensajes por sesión/minuto. Las ventanas son minutos UTC. No se confía en un `X-Forwarded-For` enviado arbitrariamente; configurar los proxies confiables de Uvicorn antes de desplegar detrás de un proxy para conservar la IP real.

## Ejemplo de conexión desde el widget existente

```js
const base = 'https://HOST_PUBLICO_OMNIAGENT';
const siteId = 'PUBLIC_ID_REGISTRADO';
async function jsonRequest(path, {token, body, method = 'GET'} = {}) {
  const response = await fetch(base + path, {
    method,
    headers: {
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      ...(body ? {'Content-Type': 'application/json'} : {}),
    },
    ...(body ? {body: JSON.stringify(body)} : {}),
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}
const session = await jsonRequest('/api/v1/widget/session', {
  method: 'POST', body: {site_id: siteId},
});
const path = `/api/v1/widget/conversations/${session.conversation_id}/messages`;
const pending = {content: 'Necesito asistencia', idempotency_key: crypto.randomUUID()};
await jsonRequest(path, {method: 'POST', token: session.token, body: pending});
// Ante timeout, reutilizar pending; no crear otra clave.
let cursor = 0;
async function poll() {
  let page;
  do {
    page = await jsonRequest(`${path}?after_id=${cursor}&limit=50`, {token: session.token});
    // Renderizar page.messages con textContent o interpolación escapada, nunca innerHTML.
    cursor = page.next_after_id;
  } while (page.has_more);
}
await poll();
// Conectar poll al temporizador y al ciclo de visibilidad del widget existente.
```

El ejemplo muestra el contrato; el widget debe implementar estado de error, reintentos con espera, renovación, cancelación de polling y almacenamiento del token. Preferir memoria; si se requiere reanudación tras recarga, usar sessionStorage y proteger el sitio contra XSS. Nunca escribir tokens en logs o URLs. No insertar código de ejemplo sin adaptar su ciclo de vida.

## Validación pendiente en ambos repositorios

Desde Mosfix, crear sesión; enviar un mensaje; verlo en OmniAgent bajo `website`; responder como operador; recuperar esa respuesta mediante polling. Después probar reintento del mismo UUID, recarga, expiración, origen distinto, dos visitantes simultáneos, conversación cerrada y desactivación del sitio. Esta validación necesita el widget real y un entorno de integración autorizado; las pruebas locales de OmniAgent no la sustituyen.
