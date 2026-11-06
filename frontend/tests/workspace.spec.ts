import AxeBuilder from '@axe-core/playwright'
import {test,expect,type Page} from '@playwright/test'
async function navigate(page:Page,name:string){
 const toggle=page.getByRole('button',{name:'Abrir navegación',exact:true})
 if(page.viewportSize()!.width<760){await expect(toggle).toBeVisible();await toggle.click()}
 await page.locator('.sidebar').getByRole('link',{name:new RegExp('^'+name+'(?: |$)')}).click()
}
test('demo remains local and responsive in both themes',async({page})=>{
 const errors:string[]=[],calls:string[]=[]
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))calls.push(r.url())})
 await page.goto('/login');await page.getByRole('button',{name:/Entrar al modo/}).click()
 await expect(page.getByRole('heading',{name:/Todo conectado/})).toBeVisible()
 await navigate(page,'Conversaciones')
 await page.locator('.conversation-item').first().click()
 await page.getByLabel('Escribe una respuesta').fill('Borrador conservado')
 const back=page.getByRole('button',{name:'Volver a la lista'})
 if(await back.isVisible())await back.click()
 await page.locator('.conversation-item').nth(1).click()
 if(await back.isVisible())await back.click()
 await page.locator('.conversation-item').first().click()
 await expect(page.getByLabel('Escribe una respuesta')).toHaveValue('Borrador conservado')
 await page.getByRole('button',{name:'Simular respuesta'}).click()
 await expect(page.locator('.bubble').filter({hasText:'Borrador conservado'})).toHaveCount(1)
 await page.getByRole('button',{name:'Cambiar modo claro u oscuro'}).click()
 await expect(page.locator('html')).toHaveClass(/dark/)
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
 await page.screenshot({path:test.info().outputPath('inbox-dark.png')})
 expect(errors).toEqual([]);expect(calls).toEqual([])
})
test('organization discovery, website reply and internal note use matching contracts',async({page})=>{
 const calls:{path:string;body:any}[]=[],messages:any[]=[{id:1,tenant_id:7,conversation_id:11,direction:'inbound',content:'Consulta del visitante',created_at:'2026-11-05T12:00:00Z'}]
 await page.route('**/api/**',async route=>{
  const r=route.request(),path=new URL(r.url()).pathname.replace('/api',''),body=r.postDataJSON();calls.push({path,body})
  let data:any=[]
  if(path==='/auth/login')data={access_token:'test-token',token_type:'bearer'}
  else if(path==='/auth/me')data={id:3,email:'owner@example.com',is_active:true}
  else if(path==='/auth/organizations')data=[{tenant_id:7,organization:'Mosfix',role:'owner'},{tenant_id:8,organization:'Other',role:'agent'}]
  else if(path==='/tenants/7/me')data={tenant_id:7,organization:'Mosfix',role:'owner'}
  else if(path.endsWith('/customers'))data=[{id:9,tenant_id:7,external_id:'web:visitor',name:'Visitante',created_at:'2026-11-05T12:00:00Z'}]
  else if(path.endsWith('/conversations'))data=[{id:11,tenant_id:7,customer_id:9,channel:'website',status:'open',created_at:'2026-11-05T12:00:00Z',unread:true,pending_reply:true,automation_enabled:true}]
  else if(path==='/tenants/7/messages'&&r.method()==='POST'){data={...body,id:2,tenant_id:7,created_at:'2026-11-05T12:01:00Z',delivery_status:'available'};messages.push(data)}
  else if(path.endsWith('/conversations/11/messages'))data=messages
  else if(path.endsWith('/stats'))data={customers:1,conversations:1,open_conversations:1,inbound_messages:1,outbound_messages:0}
  else if(path.endsWith('/members'))data=[{user_id:3,email:'owner@example.com',role:'owner'}]
  await route.fulfill({json:data})
 })
 await page.goto('/login');await page.getByLabel('Correo electrónico').fill('owner@example.com');await page.getByLabel('Contraseña').fill('password')
 await page.getByRole('button',{name:'Iniciar sesión'}).click()
 await page.getByLabel('Organización',{exact:true}).selectOption('7')
 await page.getByRole('button',{name:'Iniciar sesión'}).click()
 await navigate(page,'Conversaciones');await page.locator('.conversation-item').click()
 await page.getByLabel('Escribe una respuesta').fill('Hola Mosfix');await page.getByRole('button',{name:'Enviar respuesta'}).click()
 await expect(page.locator('.bubble').filter({hasText:'Hola Mosfix'})).toContainText('Disponible para el visitante')
 const sent=calls.find(c=>c.path==='/tenants/7/messages')!
 expect(sent.body.idempotency_key).toBeTruthy();expect(sent.body.direction).toBe('outbound')
 await page.locator('.operator-tools summary').click();await page.getByLabel('Nota interna',{exact:true}).fill('Solo equipo');await page.getByRole('button',{name:'Guardar nota'}).click()
 await expect.poll(()=>calls.some(c=>c.path.endsWith('/notes')&&c.body.content==='Solo equipo')).toBeTruthy()
 expect(calls.filter(c=>c.path==='/tenants/7/messages')).toHaveLength(1)
})

test('applicable WCAG AA automated checks across screens',async({page})=>{
 await page.goto('/login')
 let result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
 expect(result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.html)}))).toEqual([])
 await page.getByRole('button',{name:/Entrar al modo/}).click()
 await expect(page.getByRole('heading',{name:/Todo conectado/})).toBeVisible()
 for(const screen of ['Dashboard','Conversaciones','Clientes','Automatizaciones','Configuración']){
  await navigate(page,screen)
  result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
  expect(result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.html)})),screen).toEqual([])
  await page.getByRole('button',{name:'Cambiar modo claro u oscuro'}).click()
  result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
  expect(result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.html)})),screen+' dark').toEqual([])
  await page.getByRole('button',{name:'Cambiar modo claro u oscuro'}).click()
 }
})
