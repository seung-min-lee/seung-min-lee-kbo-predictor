import sys; sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page.goto('https://www.oddsportal.com/baseball/south-korea/kbo/', timeout=90000, wait_until='domcontentloaded')
    time.sleep(8)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    js = """
() => {
    const results = [];
    let currentDate = '';
    document.querySelectorAll('div.eventRow').forEach(row => {
        const dateEl = row.querySelector('[data-testid="date-header"]');
        if (dateEl && dateEl.innerText.trim()) currentDate = dateEl.innerText.trim();
        const teams = Array.from(row.querySelectorAll('p.participant-name'))
            .map(el => el.innerText.trim()).filter(Boolean).slice(0,2);
        if (teams.length < 2) return;
        const allLinks = Array.from(row.querySelectorAll('a[href]'))
            .map(a => a.href).filter(h => h && h.length > 10);
        const id = row.getAttribute('id');
        results.push({date: currentDate, teams, links: allLinks, id});
    });
    return results;
}
"""
    raw = page.evaluate(js)
    for r in raw:
        if 'Today' in r['date'] or 'Tomorrow' in r['date']:
            print(r['date'], r['teams'], '| id:', r['id'])
            for lnk in r['links']:
                print('   ->', lnk)

    browser.close()
