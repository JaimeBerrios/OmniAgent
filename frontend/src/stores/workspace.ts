import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useSession } from './session'
import { demoData } from '../data/demo'
import { api } from '../services/api'
import type {Customer,Conversation,Message,DashboardStats,DailyActivity} from '../types'
export const useWorkspace=defineStore('workspace',()=>{
 const customers=ref<Customer[]>([]), conversations=ref<Conversation[]>([]),messages=ref<Message[]>([])
 const recentMessages=ref<Message[]>([]);const loading=ref(false),error=ref('');const stats=ref<DashboardStats|null>(null);const activity=ref<DailyActivity[]>([]);let generation=0
 function reset(){generation++;customers.value=[];conversations.value=[];messages.value=[];recentMessages.value=[];stats.value=null;activity.value=[];error.value='';loading.value=false}
 window.addEventListener('workspace-reset',reset)
 async function load(){const current=++generation;loading.value=true;error.value='';try {const s=useSession();if(s.mode==='demo'){const data=demoData();customers.value=data.customers;conversations.value=data.conversations;messages.value=data.messages;recentMessages.value=[...data.messages].sort((a,b)=>b.created_at.localeCompare(a.created_at)).slice(0,10)}else if(s.tenant){const [customerResult, conversationResult, statsResult, activityResult, recentResult] = await Promise.all([
  api.customers(s.tenant.tenant_id),
  api.conversations(s.tenant.tenant_id),
  api.stats(s.tenant.tenant_id),
  api.activity(s.tenant.tenant_id),
  api.recentMessages(s.tenant.tenant_id)
]);
if (current === generation) {
  customers.value = customerResult;
  conversations.value = conversationResult;
  stats.value = statsResult;
  activity.value = activityResult;
  recentMessages.value = recentResult;
}}}catch(e){if(current===generation)error.value=(e as Error).message}finally{if(current===generation)loading.value=false}}
 async function addCustomer(name:string,external_id:string){const s=useSession(),current=generation; if(customers.value.some(c=>c.external_id===external_id))throw new Error('Ya existe un cliente con ese identificador.');const c=s.mode==='demo'?{id:Math.max(0,...customers.value.map(c=>c.id))+1,tenant_id:0,name:name||null,external_id,created_at:new Date().toISOString()}:await api.createCustomer(s.tenant!.tenant_id,{name:name||null,external_id});if(current===generation)customers.value.push(c)}
 async function createConversation(customer_id:number,channel:string){const s=useSession(),current=generation;const c=s.mode==='demo'?{id:Math.max(0,...conversations.value.map(c=>c.id))+1,tenant_id:0,customer_id,channel,status:'open',created_at:new Date().toISOString()}:await api.createConversation(s.tenant!.tenant_id,{customer_id,channel});if(current===generation)conversations.value.unshift(c);return c}
 async function loadMessages(id:number){const s=useSession(),current=generation;if(s.mode==='demo')return;const result=await api.messages(s.tenant!.tenant_id,id);if(current===generation)messages.value=[...messages.value.filter(m=>m.conversation_id!==id),...result]}
 function reply(id:number,content:string){if(useSession().mode!=='demo')return;messages.value.push({id:Date.now(),tenant_id:0,conversation_id:id,direction:'outbound',content,created_at:new Date().toISOString()})}
 return {customers,conversations,messages,recentMessages,stats,activity,loading,error,reset,load,addCustomer,createConversation,loadMessages,reply}
})
