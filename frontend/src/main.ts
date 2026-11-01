import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import {router} from './router'
import './styles/main.css'
const app = createApp(App)
app.directive('modal', { mounted(el: HTMLDialogElement) { el.removeAttribute('open'); el.showModal(); el.addEventListener('cancel', event => event.preventDefault()) } })
app.use(createPinia()).use(router).mount('#app')
