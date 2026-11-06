import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, setToken } from '../services/api'
import type {Profile,Tenant} from '../types'
export const useSession = defineStore('session',()=>{
 const mode=ref<'demo'|'live'|null>(sessionStorage.getItem('omni-demo')==='true'?'demo':null)
 const profile=ref<Profile|null>(mode.value?{id:0,email:'alex@demo.example',is_active:true}:null)
 const tenant=ref<Tenant|null>(mode.value?{tenant_id:0,organization:'Mosfix',role:'owner'}:null)
 function logout(){ mode.value=null; profile.value=null;tenant.value=null;setToken('');sessionStorage.removeItem('omni-demo');window.dispatchEvent(new Event('workspace-reset')) }
 function demo(){logout();mode.value='demo';profile.value={id:0,email:'alex@demo.example',is_active:true};tenant.value={tenant_id:0,organization:'Mosfix',role:'owner'};sessionStorage.setItem('omni-demo','true')}
 async function login(email:string,password:string,id:number){logout();try {const result=await api.login(email,password);setToken(result.access_token); const user=await api.profile();const org=await api.tenant(id);profile.value=user;tenant.value=org;mode.value='live'}catch(e){logout();throw e}}
 async function authenticate(email:string,password:string){logout();try{const result=await api.login(email,password);setToken(result.access_token);profile.value=await api.profile();return await api.organizations()}catch(e){logout();throw e}}
 async function chooseOrganization(id:number){tenant.value=await api.tenant(id);mode.value='live'}
 return {mode,profile,tenant,logout,demo,login,authenticate,chooseOrganization}
})
