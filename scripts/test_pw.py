from playwright.sync_api import sync_playwright
import time
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(viewport={'width':1920,'height':1080})
    page = ctx.new_page()
    page.goto('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    page.wait_for_selector('div.eventRow', timeout=20000)
    time.sleep(2)
    count = page.evaluate("() => document.querySelectorAll('div.eventRow').length")
    print(f'eventRow 수: {count}')
    browser.close()
print('Playwright 정상 동작')
