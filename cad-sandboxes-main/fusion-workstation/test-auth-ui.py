"""Exercise the actual UI in Chromium with deterministic API responses."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parent/'connector-ui'
BASE='http://127.0.0.1:19888/test/'

def state(revision,phase,form=None,stage=1,**extra):
    return {'epoch':'test','revision':revision,'phase':phase,'stage':stage,'form':form,
            'form_token':'token' if form else None,'message':phase,'verified':False,'error':None,'can_retry':False,**extra}

async def main():
    api={'state':state(1,'credentials_required','email'),'next':None,'error':None,'posts':0}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,channel="chrome")
        page=await browser.new_page(viewport={'width':900,'height':1200})
        async def route(request):
            path=request.request.url.removeprefix(BASE)
            if path=='v1/auth':await request.fulfill(json=api['state'])
            elif path=='v1/auth/credentials':
                api['posts']+=1
                if api['error']:await request.fulfill(status=409,json={'error':{'code':'form_disabled','message':api['error']}})
                else:await request.fulfill(json={'accepted':True,'state':api['next']})
            elif path=='theme.css':await request.fulfill(body=(ROOT.parents[1]/'click-to-ship'/'web'/'theme.css').read_bytes(),content_type='text/css')
            elif path in ('','app.js','style.css'):
                name=path or 'index.html';mime={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]
                await request.fulfill(body=(ROOT/name).read_bytes(),content_type=mime)
            else:await request.fulfill(status=404,body='')
        await page.route(BASE+'**',route)
        await page.goto(BASE)
        await expect(page.locator('#email')).to_be_visible()
        await expect(page.locator('#password')).to_be_hidden()
        await page.locator('#email').fill('synthetic@example.invalid')
        api['next']=state(2,'submitting','email')
        await page.locator('#submit-auth').click()
        await expect(page.locator('#submit-auth')).to_be_disabled()
        await page.wait_for_timeout(1700) # stale GET must not reverse accepted POST
        await expect(page.locator('#submit-auth')).to_be_disabled()
        assert await page.locator('#steps li.done').count()==1
        api['state']=state(3,'password_required','password')
        await expect(page.locator('#password')).to_be_visible()
        await expect(page.locator('#password')).to_be_enabled()
        await expect(page.locator('#email')).to_be_hidden()
        await page.locator('#password').fill('synthetic-password')
        api['error']='Autodesk disabled this form. Wait for it to finish loading.'
        await page.locator('#submit-auth').click()
        await expect(page.locator('#form-error')).to_have_text(api['error'])
        await expect(page.locator('#password')).to_have_value('synthetic-password')
        assert await page.locator('#steps li.done').count()==1
        api['error']=None;api['next']=state(4,'submitting','password')
        await page.locator('#submit-auth').click()
        await expect(page.locator('#password')).to_have_value('')
        await expect(page.locator('#submit-auth')).to_be_disabled()
        api['state']=state(5,'code_required','code')
        await expect(page.locator('#code')).to_be_visible()
        await expect(page.locator('#password')).to_be_hidden()
        await page.evaluate('s=>render(s)',state(4,'password_required','password'))
        await expect(page.locator('#code')).to_be_visible()
        api['state']=state(6,'session_expired',can_retry=True,error='Session expired')
        await expect(page.locator('#retry')).to_be_visible()
        await expect(page.locator('#auth-form')).to_be_hidden()
        await expect(page.locator('#form-error')).to_have_text('Session expired')
        assert await page.locator('#steps li.done').count()==1
        api['state']=state(7,'opening_fusion',stage=2)
        await expect(page.locator('#retry')).to_be_hidden()
        assert await page.locator('#steps li.done').count()==2
        await expect(page.locator('#open-viewer')).to_be_hidden()
        api['state']=state(8,'ready',stage=3,verified=True)
        await expect(page.locator('#open-viewer')).to_be_visible()
        assert await page.locator('#steps').is_hidden()
        assert await page.locator('.auth-footer').is_hidden()
        await browser.close()
    print(json.dumps({'passed':True,'checks':['one field per VM screen','submission remains locked','stale poll ignored','specific error retained','password retained on pre-submit rejection','password cleared after acknowledgment','MFA transition','expiry recovery','no premature ready'],'submissions':api['posts']}))

asyncio.run(main())
