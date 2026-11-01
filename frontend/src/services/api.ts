import type { Customer, Conversation, Message, Profile, Tenant } from '../types'
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
 profile:()=>request<Profile>('/auth/me'),
 tenant:(id:number)=>request<Tenant>(`/tenants/${id}/me`),
 customers:(id:number)=>request<Customer[]>(`/tenants/${id}/customers`),
 createCustomer:(id:number,data:{name:string|null;external_id:string})=>post<Customer>(`/tenants/${id}/customers`,data),
 createConversation:(id:number,data:{customer_id:number;channel:string})=>post<Conversation>(`/tenants/${id}/conversations`,data),
 messages:(id:number,conversation:number)=>request<Message[]>(`/tenants/${id}/conversations/${conversation}/messages`),
}
