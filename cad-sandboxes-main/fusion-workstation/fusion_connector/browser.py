"""Drive only the VM's Autodesk sign-in tab; never return input values."""
import json
from pathlib import Path
from contextlib import contextmanager
import re
import urllib.request
import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

TRANSPORT=Path(__file__).with_suffix('.ps1').read_text()
GUARD="""
if(location.protocol!=='https:' || !['signin.autodesk.com','accounts.autodesk.com'].includes(location.hostname)) throw Error('Untrusted page');
const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
const inputs=[...document.querySelectorAll('input')].filter(visible);
const buttons=[...document.querySelectorAll('button,input[type=submit]')].filter(visible);
"""
INSPECT=GUARD+"""
const page_id=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(location.href)))].map(b=>b.toString(16).padStart(2,'0')).join('');
return {title:document.title,page_id,
 inputs:inputs.map(e=>({type:e.type,id:e.id,name:e.name,autocomplete:e.autocomplete,placeholder:e.placeholder,disabled:e.disabled||e.readOnly})),
 buttons:buttons.map(e=>({text:(e.innerText||e.value||'').trim(),disabled:e.disabled})),
 errors:[...document.querySelectorAll('[role=alert],.MuiFormHelperText-root.Mui-error')].filter(visible).map(e=>e.innerText),
 text:document.body.innerText.slice(0,5000)};
"""


class AutodeskBrowser:
    def __init__(self,vm):self.vm=vm
    @contextmanager
    def page(self):
        endpoint=self.vm.connect_browser()
        info=json.load(urllib.request.urlopen(endpoint+'/json/version',timeout=3))
        remote=urllib.parse.urlsplit(info['webSocketDebuggerUrl'])
        websocket='ws://'+urllib.parse.urlsplit(endpoint).netloc+remote.path
        with sync_playwright() as driver:
            browser=driver.chromium.connect_over_cdp(websocket,timeout=5000)
            pages=[p for c in browser.contexts for p in c.pages if trusted(p.url)]
            if not pages:raise RuntimeError('No Autodesk sign-in page')
            # Native login can leave an older tab open. Prefer the latest page.
            yield pages[-1]
    def evaluate(self,script):
        with self.page() as page:return page.evaluate('(async()=>{'+script+'})()')
    def inspect(self):return self.evaluate(INSPECT)
    def confirm(self,label):
        if label not in ("Don't trust this device",'Open Product'):raise ValueError('Unsupported confirmation')
        with self.page() as page:
            button=page.get_by_role('button',name=label,exact=True).element_handle()
            if not button or not button.is_visible() or not button.is_enabled():return False
            if not button.evaluate("e=>location.protocol==='https:' && ['signin.autodesk.com','accounts.autodesk.com'].includes(location.hostname)"):return False
            button.click(timeout=3000);return True
    def fill_code(self,page,value):
        if not trusted(page.url):return {'filled':False,'reason':'stale_form'}
        pins=[e for e in page.locator('input[id^="pin-"]').element_handles() if e.is_visible()]
        if len(pins)>1:
            if len(value)!=len(pins) or not value.isascii() or not value.isdigit():
                return {'filled':False,'reason':'invalid_code_length'}
            if not all(e.is_enabled() for e in pins):return {'filled':False,'reason':'form_disabled'}
            for field,digit in zip(pins,value):field.fill(digit,timeout=2000)
            # Verify completeness inside the VM browser. Never return the code.
            complete=pins[0].evaluate('(el,code)=>[...el.ownerDocument.querySelectorAll(\'input[id^="pin-"]\')].filter(e=>e.offsetWidth||e.offsetHeight).map(e=>e.value).join(\'\')===code',value)
            return {'filled':complete,'reason':None if complete else 'incomplete_code'}
        field=page.locator('input[autocomplete=one-time-code],input[name=code],input[id*=code i],input[name=otp],input[name=otc],input[name=verificationCode],input[inputmode=numeric]').first
        field.fill(value,timeout=3000)
        return {'filled':True}
    def submit(self,kind,value,page_id):
        selectors={
            'email':'input#userName,input[type=email]',
            'password':'input[type=password]',
            'code':'input[autocomplete=one-time-code],input[name=code],input[id*=code i],input[name=otp],input[name=otc],input[name=verificationCode],input[inputmode=numeric]'}
        if kind not in selectors:raise ValueError('Unsupported sign-in field')
        with self.page() as page:
            current=page.evaluate('(async()=>{'+INSPECT+'})()')
            if current['page_id']!=page_id:return {'submitted':False,'reason':'stale_form'}
            fields=page.locator(selectors[kind]).element_handles()
            field=next((f for f in fields if f.is_visible()),None)
            if not field or not field.is_enabled():return {'submitted':False,'reason':'form_disabled'}
            # An ElementHandle stays bound to its original document. If the
            # page navigates, filling fails instead of resolving on a new host.
            if not field.evaluate("e=>location.protocol==='https:' && ['signin.autodesk.com','accounts.autodesk.com'].includes(location.hostname)"):
                return {'submitted':False,'reason':'stale_form'}
            button=page.get_by_role('button',name=re.compile(r'^(next|sign in|verify|continue|submit)$',re.I)).element_handle()
            if not button:return {'submitted':False,'reason':'no_submit_button'}
            if kind=='code':
                filled=self.fill_code(page,value.strip())
                if not filled['filled']:return {'submitted':False,'reason':filled['reason']}
            else:field.fill(value,timeout=3000)
            try:
                button.wait_for_element_state('enabled',timeout=2000)
                button.click(timeout=3000)
            except PlaywrightTimeout:
                try:field.fill('',timeout=1000)
                except Exception:pass
                return {'submitted':False,'reason':'form_disabled'}
            return {'submitted':True}


def trusted(value):
    p=urllib.parse.urlsplit(value)
    return p.scheme=='https' and p.hostname in ('signin.autodesk.com','accounts.autodesk.com') and p.port in (None,443) and not p.username and not p.password
