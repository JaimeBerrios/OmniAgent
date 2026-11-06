<script setup lang="ts">
import {ref,watch} from 'vue'
import {api,type ConversationEvent} from '../services/api'
import {useSession} from '../stores/session'
import type {Conversation} from '../types'
import Notice from './Notice.vue'
const props=defineProps<{conversation:Conversation}>(),emit=defineEmits<{updated:[]}>(),s=useSession()
const events=ref<ConversationEvent[]>([]),note=ref(''),error=ref(''),busy=ref(false),members=ref<{user_id:number;email:string;role:string}[]>([])
let generation=0
watch(()=>props.conversation.id,async id=>{const current=++generation;events.value=[];note.value='';error.value='';try{const [e,m]=await Promise.all([api.events(s.tenant!.tenant_id,id),api.members(s.tenant!.tenant_id)]);if(current===generation){events.value=e;members.value=m}}catch(e){if(current===generation)error.value=(e as Error).message}},{immediate:true})
async function run(action:()=>Promise<unknown>){busy.value=true;error.value='';try{await action();emit('updated')}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function addNote(){const id=props.conversation.id;await api.note(s.tenant!.tenant_id,id,note.value);note.value='';events.value=await api.events(s.tenant!.tenant_id,id)}
</script>
<template><details class="operator-tools"><summary>Herramientas del equipo <span v-if="!conversation.automation_enabled" class="chip">Intervención humana</span></summary><Notice v-if="error" error>{{error}}</Notice><div class="operator-actions"><label>Asignación<select aria-label="Asignación" :value="conversation.assigned_user_id||''" :disabled="busy" @change="run(()=>api.assign(s.tenant!.tenant_id,conversation.id,Number(($event.target as HTMLSelectElement).value)||null))"><option value="">Sin asignar</option><option v-for="m in members" :key="m.user_id" :value="m.user_id">{{m.email}}</option></select></label><button class="button" :disabled="busy" @click="run(()=>api.intervention(s.tenant!.tenant_id,conversation.id,!conversation.automation_enabled))">{{conversation.automation_enabled?'Tomar control humano':'Permitir automatización'}}</button><button class="button" :disabled="busy" @click="run(()=>api.read(s.tenant!.tenant_id,conversation.id))">Marcar como leída</button></div><form class="note-form" @submit.prevent="run(addNote)"><label>Nota interna<textarea v-model="note" maxlength="4096" required placeholder="Solo visible para el equipo"></textarea></label><button class="button" :disabled="busy||!note.trim()">Guardar nota</button></form><ol class="event-list"><li v-for="e in events" :key="e.id"><strong>{{e.kind==='note'?'Nota interna':e.kind}} · Agente #{{e.actor_id}}</strong><p>{{e.content}}</p></li></ol></details></template>
