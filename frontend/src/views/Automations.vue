<script setup lang="ts">import {ref, onMounted} from 'vue';
import {api, type AutomationStatus} from '../services/api';
import {useSession} from '../stores/session';
import {Workflow,Webhook,SlidersHorizontal,Split,Database,ArrowRight,ChevronDown} from 'lucide-vue-next';import Notice from '../components/Notice.vue';const expanded=ref(true);
const session = useSession();
const telemetry = ref<AutomationStatus | null>(null);
const loading = ref(false);
const error = ref('');

const canView = () =>
  session.mode === 'live' &&
  !!session.tenant &&
  ['owner', 'admin'].includes(session.tenant.role);

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleString('es-SV') : 'No disponible';


const executionLabel = (status: string | null) => ({
  success: 'Completada',
  error: 'Error',
  running: 'En ejecución',
  waiting: 'En espera',
  canceled: 'Cancelada',
  crashed: 'Interrumpida',
}[status || ''] || status || 'Desconocido');

const executionClass = (status: string | null) =>
  status === 'success' ? 'open' :
  ['error', 'crashed', 'canceled'].includes(status || '') ? 'pending' :
  '';

const executionDuration = (start: string | null, end: string | null) => {
  if (!start || !end) return '—';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '—';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
};

onMounted(async () => {
  if (!canView() || !session.tenant) return;

  loading.value = true;

  try {
    telemetry.value = await api.automationsStatus(session.tenant.tenant_id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Error al consultar n8n';
  } finally {
    loading.value = false;
  }
});
const steps=[{icon:Webhook,title:'Recepción',description:'El webhook recibe el evento entrante.'},{icon:SlidersHorizontal,title:'Normalización',description:'Se preparan el cliente y el mensaje.'},{icon:Database,title:'Registro entrante',description:'El servicio persiste el mensaje en la API.'},{icon:Split,title:'Clasificación',description:'El flujo selecciona la respuesta correspondiente.'},{icon:Database,title:'Registro saliente',description:'La respuesta se registra mediante el servicio.'}];</script>
<template><div class="page-heading"><div><div class="eyebrow">MENOS TAREAS. MÁS CONEXIONES.</div><h1>Automatizaciones</h1><p>Entiende cómo se mueve cada mensaje detrás de la conversación.</p></div><span class="chip"><Workflow :size="15"/>Diseño del flujo</span></div><Notice v-if="session.mode === 'demo'">
Modo demostración: la telemetría de n8n no está disponible.
</Notice>
<Notice v-else-if="!canView()">
La telemetría está disponible únicamente para administradores.
</Notice>
<Notice v-else-if="error">
{{ error }}
</Notice>
<Notice v-else>
Estado operativo consultado desde n8n mediante la API autenticada de OmniAgent. Esta vista es de solo lectura.
</Notice><section class="automation-hero card"><div class="automation-hero-icon"><Workflow :size="32"/></div><div><span class="eyebrow">WORKFLOW · N8N</span><h2>Recepción de mensajes</h2><p>Del primer contacto al registro de la respuesta, con contexto de organización.</p></div><span class="status pending" v-if="loading">Consultando...</span>
<span class="status pending" v-else-if="telemetry">
{{ telemetry.workflow.active ? 'Activo' : 'Inactivo' }}
</span>
<span class="status pending" v-else>Sin telemetría</span></section><section class="card flow-card"><div class="card-heading"><div><h2>Un mensaje, un recorrido claro</h2><p>Representación simplificada del flujo existente.</p></div></div><div class="flow"><template v-for="(step,i) in steps" :key="step.title"><div class="flow-step"><span class="step-number">0{{i+1}}</span><component :is="step.icon" :size="25"/><h3>{{step.title}}</h3><p>{{step.description}}</p></div><ArrowRight v-if="i<steps.length-1" class="flow-arrow" :size="20"/></template></div></section><div class="two-columns"><section class="card padded"><h2>Estado de ejecución</h2><div v-if="telemetry">
<p><strong>Workflow:</strong> {{ telemetry.workflow.name }}</p>
<p><strong>Estado:</strong> {{ telemetry.workflow.active ? 'Activo' : 'Inactivo' }}</p>
<p><strong>Ejecuciones consultadas:</strong> {{ telemetry.executions.length }}</p>
<h3>Ejecuciones recientes</h3>
<div v-if="!telemetry.executions.length" class="empty">
No hay ejecuciones registradas.
</div>
<div v-if="telemetry.executions.length" class="table-scroll">
<table>
<thead>
<tr>
<th>ID</th>
<th>Estado</th>
<th>Inicio</th>
<th>Duración</th>
</tr>
</thead>
<tbody>
<tr v-for="execution in telemetry.executions" :key="execution.id">
<td>{{ execution.id }}</td>
<td>
<span class="status" :class="executionClass(execution.status)">
{{ executionLabel(execution.status) }}
</span>
</td>
<td>{{ formatDate(execution.started_at) }}</td>
<td>{{ executionDuration(execution.started_at, execution.stopped_at) }}</td>
</tr>
</tbody>
</table>
</div>
</div>
<div v-else class="empty">
<Workflow :size="28"/>
<h3>{{ loading ? 'Consultando n8n...' : 'Sin telemetría disponible' }}</h3>
<p>{{ error || 'No hay datos operativos disponibles para esta sesión.' }}</p>
</div></section><section class="card padded"><button class="disclosure" :aria-expanded="expanded" @click="expanded=!expanded"><h2>Acerca de esta automatización</h2><ChevronDown :size="18"/></button><div v-if="expanded"><dl><dt>Origen</dt><dd>Workflow de recepción del repositorio</dd><dt>Procesamiento</dt><dd>Normalización y selección de respuesta</dd><dt>Persistencia</dt><dd>Mensajes entrantes y salientes</dd><dt>Administración</dt><dd>Consulta autenticada de solo lectura mediante FastAPI</dd></dl><Notice>Las credenciales y los endpoints de servicio permanecen fuera del navegador.</Notice></div></section></div></template>
