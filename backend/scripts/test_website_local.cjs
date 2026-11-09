/** Isolated local E2E. No migrations, continuous workers, external site requests or real customers. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const mosfix = process.env.MOSFIX_REPO || path.resolve(root, '../mosfix');
const api = 'http://127.0.0.1:8000';
const apiContainer = process.env.OMNI_API_CONTAINER || 'omniagent-api-1';
const env = Object.fromEntries(fs.readFileSync(path.join(root,'infrastructure/.env'),'utf8').split('\n').filter(x=>x.includes('=')&&!x.trim().startsWith('#')).map(x=>{const i=x.indexOf('=');return [x.slice(0,i).trim(),x.slice(i+1).trim().replace(/^(['"])(.*)\1$/,'$2')];}));
function db(code) {
    return JSON.parse(execFileSync('docker',['exec','-i',apiContainer,'python','-'], {input:code,encoding:'utf8',timeout:60000}));
}
const prefix = 'import json,os\nfrom sqlalchemy import text\nfrom app.database import SessionLocal\n';
let browser, cid, testSite;
(async()=>{
    const response=await fetch('http://127.0.0.1:5678/api/v1/workflows/WIoAgLGVugSezGQV',{headers:{'X-N8N-API-KEY':env.N8N_PUBLIC_API_KEY}});
    assert.equal(response.status,200);
    const workflow=await response.json();
    assert.equal(workflow.active,true,'Workflow must already be active; this script never activates it');
    const exported=JSON.parse(fs.readFileSync(path.join(root,'omniagent-workflow-website.json')));
    assert.deepEqual(workflow.nodes,exported.nodes,'Live nodes differ from reviewed JSON');
    const html=fs.readFileSync(path.join(mosfix,'index.html'),'utf8');
    const configuredPublicId=html.match(/data-site-id="([^"]+)"/)[1];
    const registeredSite=db(prefix+`with SessionLocal() as d:\n r=d.execute(text('SELECT id,tenant_id,origin,is_active FROM website_sites WHERE public_id=:p'),{'p':${JSON.stringify(configuredPublicId)}}).mappings().one()\n assert r['is_active'] and str(r['tenant_id'])==os.environ['N8N_TENANT_ID']\n print(json.dumps(dict(r)))\n`);
    // A registered loopback origin isolates the test from the public Mosfix site.
    testSite=db(prefix+`import secrets\nfrom app.models import WebsiteSite\nwith SessionLocal.begin() as d:\n s=WebsiteSite(tenant_id=${registeredSite.tenant_id},public_id=secrets.token_urlsafe(24),name='Mosfix LOCAL E2E',origin='https://localhost:8443')\n d.add(s)\n d.flush()\n print(json.dumps({'id':s.id,'tenant_id':s.tenant_id,'origin':s.origin,'public_id':s.public_id}))\n`);
    const site=testSite, publicId=site.public_id;
    const preflight=await fetch(api+'/api/v1/widget/session',{method:'OPTIONS',headers:{Origin:site.origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Content-Type'}});
    assert.equal(preflight.status,204);
    assert.equal(preflight.headers.get('access-control-allow-origin'),site.origin);
    const forbidden=await fetch(api+'/api/v1/widget/session',{method:'OPTIONS',headers:{Origin:'https://unregistered.invalid','Access-Control-Request-Method':'POST'}});
    assert.equal(forbidden.status,403);
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
    const context=await browser.newContext();
    await context.grantPermissions(['local-network-access'], {origin:site.origin});
    const page=await context.newPage();
    page.on('console',message=>{if(message.type()==='error')console.error('Browser error: '+message.text().replace(/Bearer \S+/g,'Bearer [redacted]'));});
    page.on('requestfailed',request=>console.error('Browser request failed: '+new URL(request.url()).pathname+' '+request.failure()?.errorText));
    // Serve only a local fixture at the registered origin. All actual API traffic uses loopback.
    await page.route('**/*',route=>{
        const u=route.request().url();
        if(u===site.origin+'/__omniagent_local_e2e__')return route.fulfill({contentType:'text/html',body:`<omniagent-chat data-api-url="${api}" data-site-id="${publicId}"></omniagent-chat>`});
        if(u.startsWith(api+'/'))return route.continue();
        return route.abort();
    });
    await page.goto(site.origin+'/__omniagent_local_e2e__');
    await page.addScriptTag({content:fs.readFileSync(path.join(mosfix,'assets/js/omniagent-widget.js'),'utf8')});
    await page.locator('#oaLauncher').click();
    await page.waitForFunction(()=>document.querySelector('omniagent-chat')._session?.token).catch(async()=>{throw new Error('Session unavailable: '+await page.locator('#oaStatusText').textContent());});
    cid=await page.evaluate(()=>document.querySelector('omniagent-chat')._session.conversation_id);
    await page.locator('#oaInput').fill('Prueba local aislada: mi lavadora no enciende. ¿Qué información necesitan para atenderme?');
    await page.locator('#oaSubmitBtn').click();
    await page.locator('.oa-msg-visitor').waitFor();
    const before=db(prefix+`with SessionLocal.begin() as d:\n d.execute(text("UPDATE customers SET name='Mosfix LOCAL E2E' WHERE id=(SELECT customer_id FROM conversations WHERE id=:c AND tenant_id=:t)"),{'c':${cid},'t':${site.tenant_id}})\n print(json.dumps(dict(d.execute(text('SELECT id,status FROM website_inbound_events WHERE conversation_id=:c AND tenant_id=:t'),{'c':${cid},'t':${site.tenant_id}}).mappings().one())))\n`);
    assert.equal(before.status,'pending');
    const processed=db(prefix+`import uuid\nfrom app import website_worker as w\nos.environ['N8N_WEBHOOK_URL']='http://n8n:5678/webhook/omniagent-website'\nos.environ['N8N_WEBHOOK_KEY']=${JSON.stringify(env.N8N_WEBHOOK_KEY)}\nwith SessionLocal.begin() as d:\n e=dict(d.execute(text("SELECT * FROM website_inbound_events WHERE id=:id AND conversation_id=:c AND status='pending' FOR UPDATE SKIP LOCKED"),{'id':${before.id},'c':${cid}}).mappings().one())\n e['claim_token']=uuid.uuid4()\n e['attempts']+=1\n d.execute(text("UPDATE website_inbound_events SET status='processing',claim_token=:claim_token,attempts=:attempts,processing_started_at=NOW(),updated_at=NOW() WHERE id=:id"),e)\ntry:\n w.process_event(e)\nexcept Exception as error:\n w.fail_event(e,error)\n print(json.dumps({'error':type(error).__name__}))\nelse:\n with SessionLocal() as d:\n  status=d.scalar(text('SELECT status FROM website_inbound_events WHERE id=:id'),e)\n  replies=d.scalar(text("SELECT count(*) FROM messages WHERE tenant_id=:t AND conversation_id=:c AND direction='outbound' AND inbound_message_id=:m"),{'t':${site.tenant_id},'c':${cid},'m':e['message_id']})\n  print(json.dumps({'status':status,'replies':replies}))\n`);
    assert.equal(processed.status,'processed',JSON.stringify(processed));
    assert.equal(processed.replies,1);
    await page.locator('.oa-msg-agent').waitFor({timeout:20000});
    assert.ok((await page.locator('.oa-msg-agent .oa-bubble').textContent()).trim());
    await page.evaluate(async()=>{const w=document.querySelector('omniagent-chat');w._session.expires_at=new Date(Date.now()+100000).toISOString();await w._ensureSession();});
    assert.equal(await page.evaluate(()=>document.querySelector('omniagent-chat')._session.conversation_id),cid);
    console.log(JSON.stringify({result:'PASS',conversation_id:cid,event_id:before.id,outbound_count:processed.replies,cors:'PASS',widget_send_receive_display:'PASS',renewal:'PASS'}));
})().catch(error=>{console.error('Local E2E failed: '+error.name+': '+error.message);process.exitCode=1;}).finally(async()=>{
    if(browser)await browser.close();
    if(testSite)db(prefix+`with SessionLocal.begin() as d:\n d.execute(text('UPDATE website_sites SET is_active=false WHERE id=:s'),{'s':${testSite.id}})\n print(json.dumps({'test_site_deactivated':True}))\n`);
    if(cid) {
        db(prefix+`with SessionLocal.begin() as d:\n d.execute(text("UPDATE conversations SET status='closed',automation_enabled=false WHERE id=:c AND channel='website' AND customer_id IN (SELECT id FROM customers WHERE external_id LIKE 'web:%')"),{'c':${cid}})\n d.execute(text('UPDATE visitor_sessions SET revoked_at=NOW() WHERE conversation_id=:c'),{'c':${cid}})\n print(json.dumps({'isolated_conversation_closed':True}))\n`);
        console.log('Isolated conversation closed; visitor sessions revoked. Test records retained.');
    }
});
