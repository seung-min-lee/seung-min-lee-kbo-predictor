from playwright.sync_api import sync_playwright
from kbo_playwright_scrape import GAMES_URL, TEAM_MAP, normalize_date
import time
from datetime import datetime as _dt

TODAY = _dt.today().strftime('%Y-%m-%d')

JS = """() => {
    const results = [], seen = new Set();
    let cur = '';
    document.querySelectorAll('div.eventRow').forEach(row => {
        const d = row.querySelector('[data-testid="date-header"]');
        if (d && d.innerText.trim()) cur = d.innerText.trim();
        const link = row.querySelector('a[href*="/h2h/"]');
        if (!link || seen.has(link.href)) return;
        seen.add(link.href);
        const t = Array.from(row.querySelectorAll('p.participant-name')).map(e=>e.innerText.trim()).filter(Boolean).slice(0,2);
        if (t.length < 2) return;
        results.push({date: cur, home: t[0], away: t[1], url: link.href});
    });
    return results;
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=['--no-sandbox'])
    p = b.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    p.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
    p.wait_for_selector('div.eventRow', timeout=45000)
    time.sleep(3)
    raw = p.evaluate(JS)
    b.close()

n = 0
for m in raw:
    norm = normalize_date(m['date'])
    if norm != TODAY:
        continue
    n += 1
    home = TEAM_MAP.get(m['home'], m['home'])
    away = TEAM_MAP.get(m['away'], m['away'])
    print(str(n) + '. ' + home + ' vs ' + away + ' | ' + m['url'][-30:])
