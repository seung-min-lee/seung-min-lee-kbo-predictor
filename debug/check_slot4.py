"""Slot4 KT vs Lotte 현재 BM 배당 확인"""
from playwright.sync_api import sync_playwright
from kbo_playwright_scrape import GAMES_URL, TEAM_MAP, normalize_date
import json, time
from datetime import datetime as _dt

TODAY = _dt.today().strftime('%Y-%m-%d')

JS_TODAY = """
() => {
    const results = [], seen = new Set();
    let currentDate = '';
    document.querySelectorAll('div.eventRow').forEach(row => {
        const dateEl = row.querySelector('[data-testid="date-header"]');
        if (dateEl && dateEl.innerText.trim()) currentDate = dateEl.innerText.trim();
        const link = row.querySelector('a[href*="/h2h/"]');
        if (!link) return;
        const href = link.href;
        if (seen.has(href)) return;
        seen.add(href);
        const teams = Array.from(row.querySelectorAll('p.participant-name'))
            .map(el => el.innerText.trim()).filter(Boolean).slice(0, 2);
        if (teams.length < 2) return;
        results.push({date: currentDate, home: teams[0], away: teams[1], url: href});
    });
    return results;
}
"""

JS_BM_ODDS = """
() => {
    const nameEls = Array.from(document.querySelectorAll('p.height-content.pl-4'));
    const results = {};
    for (const nel of nameEls) {
        const bm = nel.innerText.trim();
        if (!bm) continue;
        let row = nel;
        for (let i = 0; i < 3; i++) row = row.parentElement;
        const cells = Array.from(row.querySelectorAll('div.odds-cell'));
        if (cells.length < 2) continue;
        const parseCell = (cell) => {
            const val = parseFloat(cell.innerText.trim());
            if (isNaN(val) || val <= 1) return null;
            const up = cell.querySelector('[class*="bg-arrowup-event"]');
            const down = cell.querySelector('[class*="bg-red-arrow"]');
            return {odds: val, dir: up ? 1 : (down ? 0 : null)};
        };
        const home = parseCell(cells[0]);
        const away = parseCell(cells[cells.length - 1]);
        if (home || away) results[bm] = {home, away};
    }
    return results;
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage','--window-size=1920,1080'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    page = ctx.new_page()
    page.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
    page.wait_for_selector('div.eventRow', timeout=45000)
    time.sleep(3)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    raw = page.evaluate(JS_TODAY)
    slot4_url = None
    for m in raw:
        norm = normalize_date(m['date'])
        if norm != TODAY:
            continue
        home = TEAM_MAP.get(m['home'], m['home'])
        away = TEAM_MAP.get(m['away'], m['away'])
        if home == 'KT Wiz Suwon' and away == 'Lotte Giants':
            slot4_url = m['url']
            slot4_home, slot4_away = home, away

    if not slot4_url:
        print('Slot4 URL 없음')
        browser.close()
        exit()

    print(f'Slot4: {slot4_home} vs {slot4_away}')
    print(f'URL: {slot4_url}')

    page.goto(slot4_url, timeout=60000, wait_until='domcontentloaded')
    time.sleep(5)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    bm_odds = page.evaluate(JS_BM_ODDS)
    browser.close()

# open 배당 불러오기
with open('kbo_today_odds.json', encoding='utf-8') as f:
    open_odds = json.load(f)
op = next((v for v in open_odds.values() if v['home'] == slot4_home), {})
h_open, a_open = op.get('home_odds'), op.get('away_odds')

print(f'\n  open: {slot4_home}={h_open} / {slot4_away}={a_open}')
print(f"\n  {'BM':<15} {'홈open':>7} {'홈now':>7} {'홈변화':>7} {'원정open':>9} {'원정now':>8} {'원정변화':>8}")
print('  ' + '-'*70)
h_changes, a_changes = [], []
for bm, data in bm_odds.items():
    h_now = (data.get('home') or {}).get('odds')
    a_now = (data.get('away') or {}).get('odds')
    h_ch = round(h_now - h_open, 3) if h_open and h_now else None
    a_ch = round(a_now - a_open, 3) if a_open and a_now else None
    if h_ch is not None: h_changes.append(h_ch)
    if a_ch is not None: a_changes.append(a_ch)
    print(f"  {bm:<15} {str(h_open):>7} {str(h_now):>7} {str(h_ch):>7} {str(a_open):>9} {str(a_now):>8} {str(a_ch):>8}")

h_avg = round(sum(h_changes)/len(h_changes), 3) if h_changes else 0
a_avg = round(sum(a_changes)/len(a_changes), 3) if a_changes else 0
signal = slot4_home if h_avg < a_avg else slot4_away
print(f'\n  평균: {slot4_home}={h_avg} / {slot4_away}={a_avg} → {signal} 정배강화')
