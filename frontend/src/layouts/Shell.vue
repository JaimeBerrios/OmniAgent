<script setup lang="ts">
import {ref,onMounted} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {LayoutDashboard,Users,MessagesSquare,Workflow,Settings,LogOut,ChevronDown,PanelLeftClose,Menu,ArrowUpRight,Command,Sun,Moon} from 'lucide-vue-next'
import {useSession} from '../stores/session';import {useWorkspace} from '../stores/workspace';import Avatar from '../components/Avatar.vue'
const session=useSession(),workspace=useWorkspace(),route=useRoute(),router=useRouter(),open=ref(false)
const nav=[{to:'/',label:'Dashboard',icon:LayoutDashboard},{to:'/conversations',label:'Conversaciones',icon:MessagesSquare},{to:'/customers',label:'Clientes',icon:Users},{to:'/automations',label:'Automatizaciones',icon:Workflow}]
function logout(){session.logout();router.push('/login')}
function theme(){const dark=document.documentElement.classList.toggle('dark');localStorage.setItem('omni-theme',dark?'dark':'light')}
onMounted(()=>workspace.load())
</script>
<template>
<div class="app-shell"><a class="skip-link" href="#main">Saltar al contenido</a><button v-if="open" class="sidebar-overlay" aria-label="Cerrar navegación" @click="open=false"></button>
<aside class="sidebar" :class="{shown:open}"><RouterLink to="/" class="brand" @click="open=false"><span class="brand-symbol"><Command :size="24"/></span>omni<span>agent</span><span class="brand-dot">.</span></RouterLink>
<div class="workspace-switch"><span class="workspace-icon">H</span><div><strong>{{session.tenant?.organization}}</strong><small>Espacio de trabajo</small></div><ChevronDown :size="15"/></div>
<p class="nav-label">WORKSPACE</p><nav><RouterLink v-for="item in nav" :key="item.to" :to="item.to" :class="{active:route.path===item.to}" @click="open=false"><component :is="item.icon" :size="19"/><span>{{item.label}}</span><span v-if="item.to==='/conversations' && session.mode==='demo'" class="nav-count">{{workspace.conversations.filter(c=>c.status==='open').length}}</span></RouterLink></nav>
<div class="sidebar-bottom"><div class="workspace-note"><span class="tiny-dot"></span>{{session.mode==='demo'?'Un espacio para explorar':'Conectado a tu organización'}}<p>{{session.mode==='demo'?'Conoce una atención más conectada. Todos los datos son de ejemplo.':'La autorización se verifica en la API.'}}</p><RouterLink to="/settings">{{session.mode==='demo'?'Acerca de esta demo':'Ver configuración'}} <ArrowUpRight :size="14"/></RouterLink></div><RouterLink to="/settings" class="settings-link" @click="open=false"><Settings :size="19"/>Configuración</RouterLink><button class="sidebar-profile" @click="logout"><Avatar :name="session.profile?.email||'Usuario'"/><span><strong>{{session.mode==='demo'?'Alex Morgan':session.profile?.email}}</strong><small>{{session.tenant?.role==='owner'?'Administrador':session.tenant?.role}}</small></span><LogOut :size="17"/><span class="sr-only">Cerrar sesión</span></button></div></aside>
<div class="main-shell"><header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu" aria-label="Abrir navegación" @click="open=true"><Menu :size="20"/></button><PanelLeftClose class="desktop-only" :size="18"/><span class="desktop-only">Workspace</span><span class="desktop-only">/</span><strong>{{route.name}}</strong></div><div class="top-actions"><span class="mode-badge"><span class="tiny-dot"></span>{{session.mode==='demo'?'Modo demostrativo':'API real'}}</span><button class="icon-button" aria-label="Cambiar modo claro u oscuro" @click="theme"><Sun :size="18"/></button><Avatar :name="session.profile?.email||'Usuario'"/></div></header>
<main id="main" tabindex="-1"><RouterView/></main><footer>OmniAgent <span>Un solo espacio. Todas tus conversaciones.</span><span>{{session.mode==='demo'?'Datos de ejemplo · Sin conexión a servicios':'Organización verificada por el backend'}}</span></footer></div></div>
</template>
