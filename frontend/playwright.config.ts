import {defineConfig} from '@playwright/test'
export default defineConfig({
 testDir:'./tests',fullyParallel:true,
 use:{baseURL:'http://127.0.0.1:4179',headless:true,reducedMotion:'reduce',
  launchOptions:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{}},
 projects:[{name:'desktop',use:{viewport:{width:1440,height:1000}}},{name:'tablet',use:{viewport:{width:768,height:1024}}},{name:'mobile',use:{viewport:{width:390,height:844}}}],
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4179',url:'http://127.0.0.1:4179',reuseExistingServer:false},
})
