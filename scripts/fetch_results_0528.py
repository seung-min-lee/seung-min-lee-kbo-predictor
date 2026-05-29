"""
2026-05-28 경기 결과를 OddsPortal에서 수집해 kbo_games.csv에 업데이트
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pandas as pd
import time

TARGET_DATE = '2026-05-28'

JS_EXTRACT = """
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
        const nums = Array.from(row.querySelectorAll('[data-v-115522af]'))
            .map(el => el.innerText.trim()).filter(t => /^\\d+$/.test(t));
        const homeScore = parseInt(nums[0]);
        const awayScore = parseInt(nums[2]);
        results.push({
            date: currentDate,
            home: teams[0] || '',
            away: teams[1] || '',
            home_score: isNaN(homeScore) ? null : homeScore,
            away_score: isNaN(awayScore) ? null : awayScore,
            finished: !isNaN(homeScore) && !isNaN(awayScore) && homeScore !== awayScore,
        });
    });
    return results;
}
"""

def normalize_date(raw):
    from datetime import datetime, timedelta
    s = str(raw).strip()
    today = datetime.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - timedelta(days=1)).strftime('%Y-%m-%d')
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1920,1080']
        )
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )

        print('OddsPortal KBO 결과 페이지 접속 중...')
        for attempt in range(3):
            try:
                page.goto('https://www.oddsportal.com/baseball/south-korea/kbo/results/', timeout=60000)
                page.wait_for_selector('div.eventRow', timeout=30000)
                break
            except PWTimeout:
                print(f'  로딩 실패 (attempt {attempt+1})')
                if attempt == 2:
                    browser.close()
                    return
                time.sleep(3)

        time.sleep(3)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)

        # 결과 수집 (여러 페이지 탐색)
        target_games = []
        for pg in range(1, 8):
            print(f'  페이지 {pg} 수집 중...')
            matches = page.evaluate(JS_EXTRACT)
            for m in matches:
                norm = normalize_date(m['date'])
                if norm == TARGET_DATE:
                    target_games.append(m)
                elif norm < TARGET_DATE and len(norm) == 10:
                    print(f'  {TARGET_DATE} 이전 날짜 도달 → 중단')
                    break
            else:
                # 다음 페이지
                went = page.evaluate("""
                    () => {
                        const cur = document.querySelector('a[data-number].active');
                        if (!cur) return false;
                        const n = parseInt(cur.getAttribute('data-number'));
                        const next = [...document.querySelectorAll('a[data-number]')]
                            .find(b => parseInt(b.getAttribute('data-number')) === n + 1);
                        if (next) { next.click(); return true; }
                        return false;
                    }
                """)
                if not went:
                    break
                try:
                    page.wait_for_selector('div.eventRow', timeout=10000)
                    time.sleep(2)
                except PWTimeout:
                    break
                continue
            break

        browser.close()

    if not target_games:
        print(f'{TARGET_DATE} 경기 결과를 찾지 못했습니다.')
        return

    # 슬롯 순서 부여
    slot_counter = 0
    games_with_slot = []
    for g in target_games:
        if g.get('finished'):
            slot_counter += 1
            if slot_counter > 5:
                break
            g['slot'] = float(slot_counter)
            winner_is_home = g['home_score'] > g['away_score']
            g['winner'] = g['home'] if winner_is_home else g['away']
            g['winner_is_home'] = winner_is_home
            games_with_slot.append(g)

    print(f'\n=== {TARGET_DATE} 경기 결과 ({len(games_with_slot)}경기) ===')
    for g in games_with_slot:
        w = 'HOME' if g['winner_is_home'] else 'AWAY'
        print(f"  slot{int(g['slot'])}: {g['home']} {g['home_score']} - {g['away_score']} {g['away']} → {w}({g['winner']}) 승")

    # kbo_games.csv 업데이트
    gdf = pd.read_csv('kbo_games.csv')
    updated = 0
    for g in games_with_slot:
        mask = (gdf['date'] == TARGET_DATE) & (gdf['slot'] == g['slot'])
        if mask.any():
            gdf.loc[mask, 'home_score']     = g['home_score']
            gdf.loc[mask, 'away_score']     = g['away_score']
            gdf.loc[mask, 'winner']         = g['winner']
            gdf.loc[mask, 'winner_is_home'] = g['winner_is_home']
            updated += 1
            print(f"  kbo_games 업데이트: slot{int(g['slot'])} {g['home']} vs {g['away']}")
        else:
            print(f"  경고: slot{int(g['slot'])} 행 없음 ({g['home']} vs {g['away']})")

    if updated:
        gdf.to_csv('kbo_games.csv', index=False, encoding='utf-8-sig')
        print(f'\nkbo_games.csv 저장 완료 ({updated}경기 업데이트)')
    else:
        print('\n업데이트된 행 없음')

if __name__ == '__main__':
    main()
