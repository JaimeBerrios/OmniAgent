import {createRouter,createWebHistory} from 'vue-router'
import {useSession} from '../stores/session'
import Shell from '../layouts/Shell.vue'
export const router=createRouter({history:createWebHistory(),routes:[{path:'/login',component:()=>import('../views/Login.vue')},{path:'/',component:Shell,children:[{path:'',name:'Dashboard',component:()=>import('../views/Dashboard.vue')},{path:'customers',name:'Clientes',component:()=>import('../views/Customers.vue')},{path:'conversations',name:'Conversaciones',component:()=>import('../views/Conversations.vue')},{path:'automations',name:'Automatizaciones',component:()=>import('../views/Automations.vue')},{path:'settings',name:'Configuración',component:()=>import('../views/Settings.vue')}]},{path:'/:pathMatch(.*)*',redirect:'/'}]})
router.beforeEach(to=>{if(!useSession().mode && to.path!=='/login')return '/login';if(useSession().mode && to.path==='/login')return '/'})
window.addEventListener('session-expired',()=>{useSession().logout();router.replace({path:'/login',query:{expired:'1'}})})
