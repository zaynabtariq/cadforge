"""Regression: Autodesk's six single-character inputs must all be filled."""
from playwright.sync_api import sync_playwright
from fusion_connector.browser import AutodeskBrowser
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,channel='chrome')
    page=browser.new_page()
    html=''.join(f'<input id="pin-{i}" maxlength="1">' for i in range(1,7))
    page.route('**/*',lambda route:route.fulfill(body=html,content_type='text/html'))
    page.goto('https://signin.autodesk.com/test')
    driver=AutodeskBrowser(None)
    assert driver.fill_code(page,'12345')['reason']=='invalid_code_length'
    assert driver.fill_code(page,'123456')['filled']
    assert page.evaluate("()=>[...document.querySelectorAll('input')].map(e=>e.value).join('')")=='123456'
    page.goto('https://untrusted.invalid/test')
    assert driver.fill_code(page,'123456')['reason']=='stale_form'
    assert page.evaluate("()=>[...document.querySelectorAll('input')].every(e=>!e.value)")
    browser.close()
print('PASS: all six digits filled; incomplete codes and untrusted pages rejected')
