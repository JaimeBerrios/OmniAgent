import type {Customer, Conversation, Message} from '../types'
const names = ['Valentina López','Diego Martínez','Camila Hernández','Andrés Flores','Sofía Ramírez','Gabriel Torres','Lucía Méndez','Daniel Castro']
export function demoData() {
 const customers: Customer[] = names.map((name,i)=>({id:i+1,tenant_id:0,external_id:`DEMO-${String(i+1).padStart(3,'0')}`,name,created_at:`2026-10-${20+i}T15:00:00Z`}))
 const conversations: Conversation[] = customers.map((c,i)=>({id:i+1,tenant_id:0,customer_id:c.id,channel:['whatsapp','instagram','messenger','web'][i%4],status:i===3 || i===6?'closed':'open',created_at:'2026-11-01T14:00:00Z'}))
 const requests = ['¡Hola! Me gustaría conocer más sobre sus planes.','¿Podrían ayudarme con mi pedido?','Hola, ¿cuál es su horario de atención?','Muchas gracias por la ayuda.','Quisiera agendar una demostración.','¿Tienen disponibilidad esta semana?','Todo resuelto, ¡gracias!','Me interesa recibir más información.']
 const messages: Message[] = conversations.flatMap((c,i)=>[{id:i*3+1,tenant_id:0,conversation_id:c.id,direction:'inbound' as const,content:requests[i],created_at:`2026-11-01T14:${String(10+i).padStart(2,'0')}:00Z`}, {id:i*3+2,tenant_id:0,conversation_id:c.id,direction:'outbound' as const,content:'¡Hola! Gracias por escribirnos. Con gusto te ayudamos. ¿Qué necesitas saber?',created_at:`2026-11-01T14:${String(20+i).padStart(2,'0')}:00Z`}])
 return {customers,conversations,messages}
}
