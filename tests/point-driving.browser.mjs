// Isolated SAMPLE fixture. No BLE connection or physical motor commands.
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'
const { chromium } = await import(process.env.BOB_PLAYWRIGHT_MODULE || 'playwright')
const root=process.cwd(), temporary=await mkdtemp(join(tmpdir(),'bob-point-browser-'))
const script=join(temporary,'serve.py')
await writeFile(script, `import sys, time, json\nfrom pathlib import Path\nfrom dataclasses import replace\nsys.path.insert(0, ${JSON.stringify(root)})\nfrom tests.test_point_driving import camera, INFO\nfrom navigation.point_drive import Runtime, create_app\nimport uvicorn\np=Path(${JSON.stringify(temporary)})\n(p/'run_info.json').write_text(json.dumps(INFO))\nr=Runtime(p,.10922,0)\nseq=0\ndef read():\n global seq\n seq+=1\n view,h,wall,_,data,_=camera(seq,seq*.03)\n now=time.time_ns()\n event=view.event.model_copy(update={'jetson_receive_ts_ns':now})\n health=h.model_copy(update={'emitted_ts_ns':now,'last_rx_ts_ns':now})\n data['event']=event.model_dump(mode='json')\n return data,replace(view,event=event),health\nr.read=read\nuvicorn.run(create_app(r,'sample-browser-token',18790),host='127.0.0.1',port=18790,log_level='error')\n`)
const server=spawn(resolve('.venv/bin/python'),[script],{stdio:'pipe'})
let output='', browser
server.stdout.on('data',data=>{output+=data})
server.stderr.on('data',data=>{output+=data})
try{
 for(let i=0;i<150;i++){
  if(server.exitCode!==null)throw Error(output)
  try{if((await fetch('http://127.0.0.1:18790/')).ok)break}catch{}
  await sleep(100)
 }
 browser=await chromium.launch({headless:true,args:['--no-sandbox']})
 const page=await browser.newPage({viewport:{width:1100,height:1000}}), errors=[]
 page.on('pageerror',error=>errors.push(error.message))
 await page.goto('http://127.0.0.1:18790/')
 await page.locator('#token').fill('sample-browser-token')
 await page.getByRole('button',{name:'Connect',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('#camera').naturalWidth>0)
 await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('SAMPLE'))
 assert.equal(await page.locator('#token').inputValue(),'','token input is cleared')
 assert.deepEqual(await page.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0],'token is not persisted')
 await sleep(400)
 const box=await page.locator('#camera').boundingBox()
 await page.locator('#camera').click({position:{x:box.width*.5,y:box.height*.7}})
 await page.waitForFunction(()=>document.querySelector('#guidance').textContent.includes('estimated'))
 await sleep(150)
 assert.match(await page.locator('#state').innerText(),/DRY_RUN/)
 const button=await page.locator('#drive').boundingBox()
 await page.mouse.move(button.x+button.width/2,button.y+button.height/2)
 await page.mouse.down()
 await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('1/30'))
 await page.mouse.up()
 await sleep(400)
 await page.waitForFunction(()=>!status.held)
 await page.screenshot({path:resolve('runs/point-driving-browser.png'),fullPage:true})
 const attempts=await page.evaluate(()=>status.attempts)
 await sleep(1200)
 assert.equal(await page.evaluate(()=>status.attempts),attempts,'release prevents another pulse')
 await page.keyboard.down('Space')
 await page.waitForFunction(previous=>status.attempts>previous,attempts)
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')))
 await page.waitForFunction(()=>!status.held)
 const afterBlur=await page.evaluate(()=>status.attempts)
 await sleep(1200)
 assert.equal(await page.evaluate(()=>status.attempts),afterBlur,'blur prevents another pulse while Space remains pressed')
 await page.keyboard.up('Space')
 await page.locator('#camera').click({position:{x:box.width*.5,y:box.height*.1}})
 await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('horizon'))
 assert.equal(await page.evaluate(()=>status.target),null,'bad click cannot reuse the old target')
 await page.evaluate(()=>socket.close())
 await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('Disconnected'))
 await sleep(100)
 // Two submits in the same task exercise replacement of a connecting socket.
 await page.evaluate(()=>{
  el('token').value='sample-browser-token';el('auth').requestSubmit();
  el('token').value='sample-browser-token';el('auth').requestSubmit();
 })
 await page.waitForFunction(()=>status?.mode==='DRY_RUN'&&socket.readyState===WebSocket.OPEN&&displayed)
 assert.equal(await page.evaluate(()=>status.held),false,'reconnect never restores a hold')
 await page.locator('#camera').click({position:{x:box.width*.5,y:box.height*.7}})
 await page.waitForFunction(()=>status.target!==null)
 await page.evaluate(()=>socket.send(JSON.stringify({kind:'hold',held:true,sequence:sequence++,ticket:'expired-ticket'})))
 await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('Disconnected'))
 assert.deepEqual(errors,[])
 console.log('Point-driving browser passed: SAMPLE dry run, image-bound target, held pulse, release, blur, rejected horizon click, reconnect without hold, expired ticket and in-memory token.')
}catch(error){
 if(browser){const pages=browser.contexts()[0]?.pages();if(pages?.length)console.error(await pages[0].locator('body').innerText());}
 console.error(output);throw error;
}finally{
 if(browser)await browser.close()
 server.kill('SIGTERM')
 await Promise.race([new Promise(done=>server.once('exit',done)),sleep(6000)])
 if(server.exitCode===null)server.kill('SIGKILL')
 await rm(temporary,{recursive:true,force:true})
}
