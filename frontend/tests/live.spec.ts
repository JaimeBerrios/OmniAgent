import {readFileSync} from 'node:fs'
import {test,expect} from '@playwright/test'
test('real local API: visitor to operator to visitor',async({page,request})=>{
 test.skip(!process.env.OMNI_BROWSER_FIXTURE,'Requires a disposable database and local FastAPI')
 const f=JSON.parse(readFileSync(process.env.OMNI_BROWSER_FIXTURE!,'utf8'))
 const origin={Origin:'https://browser-test.example'}
 const session=await request.post('/api/v1/widget/session',{headers:origin,data:{site_id:f.site}})
 expect(session.status()).toBe(201)
 const visitor=await session.json(),path=`/api/v1/widget/conversations/${visitor.conversation_id}/messages`
 const headers={...origin,Authorization:`Bearer ${visitor.token}`}
 const content='Consulta local '+crypto.randomUUID()
 expect((await request.post(path,{headers,data:{content,idempotency_key:crypto.randomUUID()}})).status()).toBe(201)
 await page.goto('/login')
 await page.getByLabel('Correo electrónico').fill(f.email);await page.getByLabel('Contraseña').fill(f.password)
 await page.getByRole('button',{name:'Iniciar sesión'}).click()
 await expect(page.getByRole('heading',{name:/Todo conectado/})).toBeVisible()
 if(page.viewportSize()!.width<760)await page.getByRole('button',{name:'Abrir navegación',exact:true}).click()
 await page.locator('.sidebar a[href="/conversations"]').click()
 await page.locator('.conversation-item').filter({hasText:content}).click()
 await expect(page.locator('.bubble').filter({hasText:content})).toHaveCount(1)
 await page.getByLabel('Escribe una respuesta').fill('Respuesta real local')
 await page.getByRole('button',{name:'Enviar respuesta'}).click()
 await expect(page.locator('.bubble').filter({hasText:'Respuesta real local'})).toHaveCount(1)
 const history=await request.get(path,{headers});expect(history.status()).toBe(200)
 expect((await history.json()).messages.some((m:any)=>m.direction==='outbound'&&m.content==='Respuesta real local')).toBeTruthy()
})
