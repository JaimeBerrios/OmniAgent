import type { Customer, Conversation, DashboardStats, DailyActivity, Message, Profile, Tenant } from '../types'

export interface AutomationExecution {
  id: string
  status: string | null
  started_at: string | null
  stopped_at: string | null
}

export interface AutomationStatus {
  workflow: {
    id: string
    name: string
    active: boolean
    archived: boolean
  }
  executions: AutomationExecution[]
}

let token = ''
export const setToken = (value: string) => { token = value }
export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
 const controller = new AbortController()
 const timeout = setTimeout(()=>controller.abort(),15000)
 try {
 const response = await fetch(`${(import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/,'')}${path}`,{...options,signal:controller.signal,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`} : {}),...options.headers}})
 const body = await response.json().catch(()=>null)
 if (!response.ok) {
  if(response.status===401 && path!=='/auth/login') window.dispatchEvent(new Event('session-expired'))
  throw new ApiError(response.status, typeof body?.detail==='string'?body.detail:response.status===422?'Revisa los datos del formulario.':`No se pudo completar la solicitud (${response.status}).`)
 }
 return body as T
 } catch(error) { if(error instanceof ApiError) throw error; throw new Error('No se pudo conectar con la API. Comprueba la dirección y la disponibilidad del backend.') } finally {clearTimeout(timeout)}
}
const post = <T>(path:string, data:unknown) => request<T>(path,{method:'POST',body:JSON.stringify(data)})
export const api = {
 login:(email:string,password:string)=>post<{access_token:string;token_type:string}>('/auth/login',{email,password}),
 organizations:()=>request<Tenant[]>('/auth/organizations'),
 profile:()=>request<Profile>('/auth/me'),
 tenant:(id:number)=>request<Tenant>(`/tenants/${id}/me`),
 automationsStatus:(id:number)=>request<AutomationStatus>(`/tenants/${id}/automations/status`),
 controlAutomation:(id:number,action:'activate'|'deactivate')=>
  request<{
   workflow:{id:string;name:string;active:boolean}
   action:'activate'|'deactivate'
  }>(`/tenants/${id}/automations/${action}`,{method:'POST'}),

 customers:async(id:number)=>{
  const all:Customer[]=[];let after=0;
  for(;;){const page=await request<Customer[]>(`/tenants/${id}/customers?limit=500&after_id=${after}`);all.push(...page);if(page.length<500)return all;after=page.at(-1)!.id}
 },
 stats:(id:number)=>request<DashboardStats>(`/tenants/${id}/stats`),
 activity:(id:number)=>request<DailyActivity[]>(`/tenants/${id}/stats/activity`),
 recentMessages:(id:number)=>request<Message[]>(`/tenants/${id}/messages/recent`),
 conversations:async(id:number,query='')=>{
  const all:Conversation[]=[];let before='';
  for(;;){const page=await request<Conversation[]>(`/tenants/${id}/conversations?limit=500${before}${query}`);all.push(...page);if(page.length<500)return all;before=`&before_id=${page.at(-1)!.id}`}
 },
 createCustomer:(id:number,data:{name:string|null;external_id:string})=>post<Customer>(`/tenants/${id}/customers`,data),
 createConversation:(id:number,data:{customer_id:number;channel:string})=>post<Conversation>(`/tenants/${id}/conversations`,data),
 updateConversationStatus:(id:number,conversationId:number,status:'open'|'closed')=>
  request<Conversation>(
   `/tenants/${id}/conversations/${conversationId}`,
   {method:'PATCH',body:JSON.stringify({status})}
  ),
 messages:async(id:number,conversation:number)=>{
  const all:Message[]=[];let after=0;
  for(;;){const page=await request<Message[]>(`/tenants/${id}/conversations/${conversation}/messages?limit=500&after_id=${after}`);all.push(...page);if(page.length<500)return all;after=page.at(-1)!.id}
 },
 members:(id:number)=>request<{user_id:number;email:string;role:string}[]>(`/tenants/${id}/members`),
 memberRole:(id:number,user:number,role:string)=>request(`/tenants/${id}/members/${user}`,{method:'PUT',body:JSON.stringify({role})}),
 websites:(id:number)=>request<Website[]>(`/tenants/${id}/websites`),
 createWebsite:(id:number,name:string,origin:string)=>post<Website>(`/tenants/${id}/websites`,{name,origin}),
 deactivateWebsite:(id:number,site:number)=>request(`/tenants/${id}/websites/${site}`,{method:'DELETE'}),
 assign:(id:number,c:number,user_id:number|null)=>request(`/tenants/${id}/conversations/${c}/assignment`,{method:'PUT',body:JSON.stringify({user_id})}),
 read:(id:number,c:number)=>post(`/tenants/${id}/conversations/${c}/read`,{}),
 intervention:(id:number,c:number,automation_enabled:boolean)=>request(`/tenants/${id}/conversations/${c}/intervention`,{method:'PUT',body:JSON.stringify({automation_enabled})}),
 note:(id:number,c:number,content:string)=>post(`/tenants/${id}/conversations/${c}/notes`,{content}),
 events:(id:number,c:number)=>request<ConversationEvent[]>(`/tenants/${id}/conversations/${c}/events`),
 sendMessage:(id:number,data:{conversation_id:number;direction:'outbound';content:string;idempotency_key:string})=>post<Message>(`/tenants/${id}/messages`,data),
}

export interface Website {id:number;public_id:string;name:string;origin:string;is_active:boolean}
export interface ConversationEvent {id:number;actor_id:number;kind:string;content:string;created_at:string}
