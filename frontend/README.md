# OmniAgent · Frontend

Vue 3 + TypeScript + Vite, Pinia, Vue Router, Tailwind CSS y Lucide. Requiere Node.js 22.12+ (o 20.19+) y npm. No necesita contenedores para la demostración.

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Abre http://localhost:5173 y selecciona **Entrar al modo demostrativo**. Los datos y respuestas son ejemplos en memoria; se reinician al recargar. La demo no llama al backend. El indicador de demo permanece visible. La gráfica del dashboard es ilustrativa.

## Integración real

En `.env`, `VITE_API_BASE_URL=/api` usa el proxy de Vite. `API_PROXY_TARGET` debe apuntar a la API accesible desde Fedora, por ejemplo a su dirección en Kali. No pongas credenciales en variables VITE. No se cambia Docker Compose ni CORS en el backend. Vite evita la necesidad de CORS durante desarrollo. En producción configura un proxy HTTPS del mismo origen para `/api` (elimina ese prefijo antes de llegar a FastAPI) y fallback a index.html para Vue Router. `vite preview` no sustituye esa configuración de producción.

Inicia sesión con correo, contraseña e ID de organización suministrados por el administrador. No existe endpoint para descubrir las organizaciones del usuario. Se consulta la membresía antes de mostrar el espacio. El JWT solo vive en memoria: recargar exige autenticarse de nuevo. Un 401 cierra sesión y limpia los datos; un 403 se presenta sin eludir autorización. Las respuestas pendientes de una sesión anterior se descartan.

### Contratos verificados en backend/app

- `POST /auth/login`: JSON `{email,password}` → `{access_token,token_type}`.
- `GET /auth/me`: Bearer JWT → `{id,email,is_active}`.
- `GET /tenants/{id}/me`: membresía → `{tenant_id,organization,role}`.
- `GET /tenants/{id}/customers`: lista `{id,tenant_id,external_id,name,created_at}`.
- `POST /tenants/{id}/customers`: `{external_id,name}`; solo owner/admin; conflicto 409.
- `POST /tenants/{id}/conversations`: `{customer_id,channel}` → registro con ID, estado y fecha. No activa canales.
- `GET /tenants/{id}/conversations/{conversation_id}/messages`: historial ordenado; consulta manual por ID o conversaciones creadas durante la sesión.

`POST /tenants/{id}/messages` existe y acepta `{conversation_id,direction,content}`, pero solo persiste mensajes. No se usa para aparentar entrega a WhatsApp u otro canal. La composición real queda deshabilitada; la demo permite simular respuestas. El navegador no consume rutas internas ni administra n8n.

### Pendiente de soporte del backend

Listado/paginación de conversaciones, búsqueda de conversaciones por cliente, métricas globales, actividad, entrega de respuestas a canales, cierre/reapertura de conversaciones, administración y telemetría de automatizaciones, listado de membresías, edición de perfil y gestión de miembros. Las métricas reales no disponibles se muestran con `—`; no se calculan a partir de listados incompletos. Solo el número de clientes corresponde al listado completo existente.

## Organización

`src/components` reutilizables; `layouts` estructura; `views` módulos; `router` protección; `stores` sesión y datos; `services` HTTP centralizado; `types` contratos; `data/demo.ts` ejemplos centralizados; `styles` identidad y responsive; `utils` formato.

```bash
npm run typecheck
npm run build
npm run preview
```

El backend es responsable del aislamiento y verifica la membresía en cada endpoint. Los filtros y permisos visuales no sustituyen esa autorización. No se persisten datos de organizaciones ni tokens en localStorage/sessionStorage; solo preferencias visuales y el indicador de modo demo.

## Validación realizada

- `npm run typecheck` y `npm run build`: correctos.
- Instalación: 0 vulnerabilidades reportadas por npm.
- Chromium headless: rutas protegidas, cinco módulos, alta/búsqueda de cliente, modal nativo, respuesta local, tema oscuro y menú móvil.
- Anchos 390, 768 y 1440 px sin desbordamiento horizontal de la página; tablas con desplazamiento propio. Capturas de escritorio y móvil inspeccionadas.
- Demo: ninguna petición a la API ni errores JavaScript durante el recorrido.
- API simulada en navegador: JSON de login, cabecera Bearer, rechazo 403 de membresía, expiración 401 y nuevo login tras recarga. No es una prueba contra FastAPI en vivo.
- Revisado el código del frontend sin credenciales de servicio ni secretos. Backend, infraestructura, migraciones y workflow sin modificaciones.
- Pendiente: prueba de integración con el backend de Kali y entrega real mediante canales externos.
