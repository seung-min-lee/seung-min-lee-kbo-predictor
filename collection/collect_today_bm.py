"""오늘 경기 BM별 현재 배당 + 방향 수집 → kbo_today_bm_odds.json 저장"""
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_os.chdir(_root); _sys.path.insert(0, _root)
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from kbo_playwright_scrape import GAMES_URL, TEAM_MAP, normalize_date, EXCLUDE
import json, time
from datetime import datetime as _dt

TODAY = _dt.today().strftime('%Y-%m-%d')
OUTPUT = 'kbo_today_bm_odds.json'

JS_TODAY_MATCHES = """
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
            // 방향: bg-arrowup-event=↑(1), bg-red-arrow=↓(0), 없으면=→(null)
            const up = cell.querySelector('[class*="bg-arrowup-event"]');
            const down = cell.querySelector('[class*="bg-red-arrow"]');
            const dir = up ? 1 : (down ? 0 : null);
            return {odds: val, dir: dir};
        };

        const home = parseCell(cells[0]);
        const away = parseCell(cells[cells.length - 1]);
        if (home || away) results[bm] = {home, away};
    }
    return results;
}
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1920,1080']
    )
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    page = ctx.new_page()

    print('오늘 경기 URL 수집 중...')
    page.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
    page.wait_for_selector('div.eventRow', timeout=45000)
    time.sleep(3)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    raw = page.evaluate(JS_TODAY_MATCHES)
    seen, matches = set(), []
    date_counter = {}
    for m in raw:
        norm = normalize_date(m['date'])
        if norm != TODAY:
            continue
        home = TEAM_MAP.get(m['home'], m['home'])
        away = TEAM_MAP.get(m['away'], m['away'])
        if (home, away) in seen:
            continue
        seen.add((home, away))
        date_counter[norm] = date_counter.get(norm, 0) + 1
        matches.append({'date': norm, 'slot': date_counter[norm],
                        'home': home, 'away': away, 'url': m['url']})

    print(f'오늘 경기 {len(matches)}개')
    all_results = {}

    for match in matches:
        slot = match['slot']
        home, away = match['home'], match['away']
        print(f'\n[Slot{slot}] {home} vs {away}')

        loaded = False
        for attempt in range(3):
            try:
                page.goto(match['url'], timeout=60000)
                page.wait_for_selector('p.height-content.pl-4', timeout=20000)
                loaded = True
                break
            except Exception as e:
                print(f'  로딩 실패 ({attempt+1}): {type(e).__name__}')
                time.sleep(3)

        if not loaded:
            print('  스킵')
            continue

        time.sleep(2)
        bm_odds = page.evaluate(JS_BM_ODDS)

        game_key = f"{match['date']}|{slot}|{home}|{away}"
        all_results[game_key] = {'date': match['date'], 'slot': slot,
                                  'home': home, 'away': away, 'bookmakers': bm_odds}

        print(f"  {'BM':<15} {'홈배당':>7} {'홈방향':>5} {'원정배당':>9} {'원정방향':>6}")
        for bm, data in bm_odds.items():
            if bm in EXCLUDE:
                continue
            h = data.get('home') or {}
            a = data.get('away') or {}
            h_dir = '↑' if h.get('dir')==1 else ('↓' if h.get('dir')==0 else '→')
            a_dir = '↑' if a.get('dir')==1 else ('↓' if a.get('dir')==0 else '→')
            print(f"  {bm:<15} {str(h.get('odds','?')):>7} {h_dir:>5} {str(a.get('odds','?')):>9} {a_dir:>6}")

    browser.close()

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f'\n저장 완료: {OUTPUT}')
