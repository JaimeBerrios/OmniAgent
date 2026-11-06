<script setup lang="ts">
import {computed,ref,watch,onMounted,onUnmounted} from 'vue';import {useRoute} from 'vue-router';import {Search,Send,Plus,ArrowLeft,MessagesSquare,X} from 'lucide-vue-next';import {useWorkspace} from '../stores/workspace';import {useSession} from '../stores/session';import ConversationTools from '../components/ConversationTools.vue';import Avatar from '../components/Avatar.vue';import Channel from '../components/Channel.vue';import Notice from '../components/Notice.vue';import {date,time} from '../utils/format'
const w=useWorkspace(),s=useSession(),route=useRoute(),search=ref(''),status=ref('all'),selected=ref<number|null>(null),draft=ref(''),error=ref(''),busy=ref(false),show=ref(false),customer=ref(''),channel=ref('whatsapp');let requestId=0
const sending=ref(false),syncError=ref('')
const drafts=ref<Record<number,string>>({}),replyKeys=new Map<number,{content:string;key:string}>(),mine=ref(false)
let timer:ReturnType<typeof setTimeout>|undefined,disposed=false
async function poll(){try{if(!document.hidden&&!busy.value&&!sending.value){await w.refreshConversations(mine.value?'&assigned_to_me=true':'');if(selected.value!==null)await w.loadMessages(selected.value);syncError.value=''}}catch(e){syncError.value=(e as Error).message}finally{if(!disposed)timer=setTimeout(poll,5000)}}
onMounted(()=>{timer=setTimeout(poll,5000)})
onUnmounted(()=>{disposed=true;clearTimeout(timer)})
watch(draft,value=>{if(selected.value!==null)drafts.value[selected.value]=value})
watch(mine,()=>w.refreshConversations(mine.value?'&assigned_to_me=true':'').catch(e=>error.value=(e as Error).message))
const items=computed(()=>w.conversations.filter(c=>(status.value==='all'||c.status===status.value)&&`${displayName(c)} ${c.id} ${c.customer_id}`.toLowerCase().includes(search.value.toLowerCase())));const conversation=computed(()=>w.conversations.find(c=>c.id===selected.value));const person=computed(()=>w.customers.find(c=>c.id===conversation.value?.customer_id));const messages=computed(()=>w.messages.filter(m=>m.conversation_id===selected.value));

function displayName(c: {
  customer_id: number;
  channel: string;
  customer_name?: string | null;
}): string {
  const customer = w.customers.find(x => x.id === c.customer_id);
  const name = customer?.name?.trim() || c.customer_name?.trim();

  if (name) return name;

  switch (c.channel.toLowerCase()) {
    case 'messenger':
    case 'facebook':
      return 'Cliente de Facebook';
    case 'instagram':
      return 'Cliente de Instagram';
    case 'whatsapp':
      return 'Cliente de WhatsApp';
    default:
      return 'Cliente';
  }
}

const selectedName = computed(() =>
  conversation.value ? displayName(conversation.value) : 'Cliente'
);

async function select(id:number){const current=++requestId;selected.value=id;error.value='';draft.value=drafts.value[id]||'';busy.value=true;try{await w.loadMessages(id)}catch(e){if(current===requestId)error.value=(e as Error).message}finally{if(current===requestId)busy.value=false}}
watch(()=>[route.query.id,w.conversations.length],()=>{const id=Number(route.query.id);if(id>0&&Number.isSafeInteger(id)&&selected.value===null)select(id)},{immediate:true})
async function create(){busy.value=true;error.value='';try{const c=await w.createConversation(Number(customer.value),channel.value);show.value=false;await select(c.id)}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function reply(){
  const content=draft.value.trim();
  if(!content||selected.value===null||busy.value||sending.value)return;
  const id=selected.value;
  error.value='';
  sending.value=true;
  try{
    if(s.mode==='demo')w.reply(id,content);
    else {
      let retry=replyKeys.get(id);if(!retry||retry.content!==content){retry={content,key:crypto.randomUUID()};replyKeys.set(id,retry)}
      await w.registerReply(id,content,retry.key);replyKeys.delete(id)
    }
    drafts.value[id]='';if(selected.value===id)draft.value='';
  }catch(e){
    error.value=(e as Error).message;
  }finally{
    sending.value=false;
  }
}
async function toggleStatus(){
  if(!conversation.value||busy.value||s.mode!=='live')return;

  const id=conversation.value.id;
  const next=conversation.value.status==='open'?'closed':'open';

  error.value='';
  busy.value=true;

  try{
    await w.changeConversationStatus(id,next);
  }catch(e){
    error.value=(e as Error).message;
  }finally{
    busy.value=false;
  }
}
</script>
<template><div class="page-heading compact"><div><div class="eyebrow">CADA MENSAJE CUENTA</div><h1>Conversaciones</h1><p>La atención empieza por escuchar.</p></div><button class="button primary" @click="show=true;error='' "><Plus :size="18"/>Nueva conversación</button></div><Notice v-if="s.mode==='demo'">Bandeja de ejemplo. Las respuestas son locales; ningún mensaje se entrega a un canal.</Notice><Notice v-else>Actualización automática cada 5 segundos. Messenger y WhatsApp usan sus colas de envío; el sitio web recupera las respuestas mediante polling. El estado muestra la confirmación disponible.</Notice>
<Notice v-if="syncError" error>La actualización automática no se pudo completar. {{syncError}}</Notice><div class="inbox card" :class="{'has-selection':selected!==null}"><section class="conversation-list" aria-label="Lista de conversaciones"><div class="inbox-list-heading"><h2>Bandeja de entrada <span class="count-badge">{{items.length}}</span></h2><label class="search-field"><Search :size="16"/><input v-model="search" placeholder="Buscar conversación…" aria-label="Buscar conversación"></label><label v-if="s.mode==='live'" class="inline-option"><input type="checkbox" v-model="mine"> Asignadas a mí</label><div class="tabs"><button v-for="tab in [{id:'all',label:'Todas'},{id:'open',label:'Abiertas'},{id:'closed',label:'Cerradas'}]" :key="tab.id" :class="{selected:status===tab.id}" @click="status=tab.id">{{tab.label}}</button></div></div><div class="conversation-scroll"><button v-for="c in items" :key="c.id" class="conversation-item" :class="{selected:selected===c.id}" @click="select(c.id)"><Avatar :name="displayName(c)" :index="c.customer_id"/><div><div class="conversation-title"><strong>{{displayName(c)}} <span v-if="c.unread" class="unread-dot" aria-label="Sin leer"></span></strong><small>{{time(w.messages.filter(m=>m.conversation_id===c.id).at(-1)?.created_at||c.last_message_at||c.created_at)}}</small></div><p>{{w.messages.filter(m=>m.conversation_id===c.id).at(-1)?.content||c.last_message||'Aún no hay mensajes'}}</p><div class="conversation-meta"><Channel :channel="c.channel"/><span v-if="c.pending_reply" class="chip">Por responder</span><span class="status" :class="c.status">{{c.status==='open'?'Abierta':'Cerrada'}}</span></div></div></button><div v-if="!items.length" class="empty"><MessagesSquare/><p>No hay conversaciones para mostrar.</p></div></div></section>
<section class="message-panel" aria-label="Historial de mensajes"><template v-if="selected!==null"><div class="chat-heading"><button class="icon-button back-inbox" aria-label="Volver a la lista" @click="selected=null;requestId++;busy=false"><ArrowLeft :size="20"/></button><Avatar :name="selectedName" :index="person?.id"/><div><h2>{{selectedName}}</h2><small>{{person?.external_id||'Historial consultado por ID'}}</small></div><div class="chat-heading-right"><button
  v-if="conversation&&s.mode==='live'"
  type="button"
  class="button"
  :disabled="busy"
  @click="toggleStatus"
>{{conversation.status==='open'?'Cerrar conversación':'Reabrir conversación'}}</button><Channel v-if="conversation" :channel="conversation.channel"/><span v-if="conversation" class="status" :class="conversation.status">{{conversation.status==='open'?'Abierta':'Cerrada'}}</span></div></div><ConversationTools v-if="conversation&&s.mode==='live'" :conversation="conversation" @updated="w.refreshConversations(mine?'&assigned_to_me=true':'')"/><Notice v-if="error" error>{{error}} <button @click="select(selected!)">Reintentar</button></Notice><div v-if="busy" class="loading" role="status">Cargando historial…</div><div v-else class="message-scroll" aria-live="polite"><div class="chat-date">{{messages.length?date(messages[0].created_at):'Una nueva conversación'}}</div><div v-if="!messages.length&&!error" class="empty"><MessagesSquare/><h3>Todo comienza con un mensaje</h3><p>{{s.mode==='demo'?'Prueba una respuesta de demostración.':'No hay mensajes en este historial.'}}</p></div><div v-for="m in messages" :key="m.id" class="message-row" :class="m.direction"><Avatar v-if="m.direction==='inbound'" :name="selectedName" :index="person?.id"/><div class="bubble"><p>{{m.content}}</p><small>{{date(m.created_at)}} · {{time(m.created_at)}} <span v-if="m.direction==='outbound'">· {{s.mode==='demo'?'Demo':['messenger','whatsapp'].includes(conversation?.channel||'')
    ?({
      pending:'Pendiente de envío',
      sending:'Enviando',
      sent:'Aceptado por Meta',
      failed:'Envío fallido',
      unknown:'Entrega sin confirmar'
    } as Record<string,string>)[m.delivery_status||'']||'Registrado'
    :conversation?.channel==='website'?'Disponible para el visitante':'Registrado'}}</span></small></div></div></div><form class="composer" @submit.prevent="reply"><label class="sr-only" for="reply">Escribe una respuesta</label><textarea id="reply" v-model="draft" rows="2" :disabled="busy||sending" :placeholder="s.mode==='demo'?'Escribe una respuesta de demostración…':'Escribe tu respuesta…'" maxlength="4096"></textarea><div><small>{{s.mode==='demo'?'Solo demostración · No se enviará a ningún canal':(conversation?.channel==='website'?'Disponible para el visitante al actualizar su widget.':'Entrega mediante el worker del canal. Consulta el estado de cada mensaje.')}}</small><button class="button primary" :disabled="!draft.trim()||busy||sending" type="submit"><Send :size="16"/>{{s.mode==='demo'?'Simular respuesta':'Enviar respuesta'}}</button></div></form></template><div v-else class="inbox-welcome"><span class="welcome-icon"><MessagesSquare :size="32"/></span><h2>Conversaciones que conectan.</h2><p>Selecciona una conversación para ver su historial<br>y darle contexto a cada respuesta.</p><span class="chip">{{s.mode==='demo'?'Espacio demostrativo':'Datos de tu organización'}}</span></div></section></div>
<dialog v-modal v-if="show" open class="modal" aria-labelledby="new-conversation" @keydown.esc="!busy&&(show=false)"><form @submit.prevent="create"><div class="card-heading"><h2 id="new-conversation">Nueva conversación</h2><button type="button" class="icon-button" aria-label="Cerrar" :disabled="busy" @click="show=false"><X :size="20"/></button></div><Notice v-if="error" error>{{error}}</Notice><label>Cliente<select v-model="customer" required><option value="" disabled>Seleccionar cliente</option><option v-for="c in w.customers" :key="c.id" :value="c.id">{{c.name||c.external_id}}</option></select></label><label>Canal<select v-model="channel"><option value="whatsapp">WhatsApp</option><option value="messenger">Messenger</option></select></label><Notice>Crear el registro no conecta ni activa el canal seleccionado.</Notice><button class="button primary full" :disabled="busy||!customer">{{busy?'Creando…':'Crear conversación'}}</button><RouterLink v-if="!w.customers.length" to="/customers" class="text-link">Primero registra un cliente</RouterLink></form></dialog></template>
