"""
오늘 예정 경기 BM별 배당 수집 → kbo_today_odds.json에 저장
1차 실행 (아침): open 배당 저장
2차 실행 (경기 1시간 전): close 배당 저장 + 방향 계산

사용: python kbo_today_scrape.py [--close]
  --close 없으면: 현재 배당을 open으로 저장
  --close 있으면: 현재 배당을 close로 저장 + today_home_dir 계산
"""
import sys, json, time
from datetime import datetime as _dt
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TODAY_ODDS_PATH = 'kbo_today_odds.json'
GAMES_URL       = 'https://www.oddsportal.com/baseball/south-korea/kbo/'
EXCLUDE         = {'My coupon', 'User Predictions', 'Betfair Exchange'}
IS_CLOSE        = '--close' in sys.argv

TEAM_MAP = {
    'Doosan Bears':'Doosan Bears','LG Twins':'LG Twins','KT Wiz':'KT Wiz Suwon',
    'SSG Landers':'SSG Landers','NC Dinos':'NC Dinos','Samsung Lions':'Samsung Lions',
    'KIA Tigers':'KIA Tigers','Lotte Giants':'Lotte Giants','Hanwha Eagles':'Hanwha Eagles',
    'Kiwoom Heroes':'Kiwoom Heroes',
}

def get_today_matches(page):
    """오늘 예정 경기 목록 + h2h URL 수집"""
    today_str = _dt.today().strftime('%Y-%m-%d')
    for attempt in range(3):
        try:
            page.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
            page.wait_for_selector('div.eventRow', timeout=45000)
            break
        except PWTimeout:
            if attempt == 2: return []
            time.sleep(5)
    time.sleep(3)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)

    raw = page.evaluate("""
    () => {
        const results = [], seen = new Set();
        let currentDate = '';
        document.querySelectorAll('div.eventRow').forEach(row => {
            const dateEl = row.querySelector('[data-testid="date-header"]');
            if (dateEl && dateEl.innerText.trim()) currentDate = dateEl.innerText.trim();
            const link = row.querySelector('a[href*="/kbo/"][href*="-"]');
            if (!link) return;
            const href = link.href;
            if (seen.has(href)) return;
            seen.add(href);
            const teams = Array.from(row.querySelectorAll('p.participant-name'))
                .map(el => el.innerText.trim()).filter(Boolean).slice(0, 2);
            if (teams.length < 2) return;
            results.push({ date: currentDate, home: teams[0], away: teams[1], url: href });
        });
        return results;
    }
    """)

    matches, slot = [], 0
    for m in raw:
        if 'Today' not in str(m['date']) and today_str not in str(m['date']):
            continue
        slot += 1
        if slot > 5: break
        home = TEAM_MAP.get(m['home'], m['home'])
        away = TEAM_MAP.get(m['away'], m['away'])
        matches.append({'date': today_str, 'slot': float(slot),
                        'home': home, 'away': away, 'url': m['url']})
    return matches


def scrape_bm_odds(page, url):
    """경기 페이지에서 BM별 홈/원정 배당 수집"""
    try:
        page.goto(url, timeout=60000, wait_until='domcontentloaded')
        page.wait_for_selector('p.height-content.pl-4', timeout=30000)
        time.sleep(3)
    except PWTimeout:
        print('  로딩 실패')
        return {}

    rows = page.evaluate("""
    () => {
        const EXCLUDE = new Set(['My coupon', 'User Predictions', 'Betfair Exchange']);
        const result = {};
        const nameEls = document.querySelectorAll('p.height-content.pl-4');
        for (const nel of nameEls) {
            const bm = nel.innerText.trim();
            if (!bm || EXCLUDE.has(bm)) continue;
            let row = nel;
            for (let i = 0; i < 3; i++) row = row.parentElement;
            // 업커밍 페이지: a.odds-link, 결과 페이지: p.odds-text 둘 다 시도
            let oddsEls = Array.from(row.querySelectorAll('a.odds-link'));
            if (!oddsEls.length) oddsEls = Array.from(row.querySelectorAll('p.odds-text'));
            if (oddsEls.length < 2) continue;
            const h = parseFloat(oddsEls[0].innerText.trim());
            const a = parseFloat(oddsEls[oddsEls.length-1].innerText.trim());
            if (!isNaN(h) && h > 1 && !isNaN(a) && a > 1) {
                result[bm] = { home: h, away: a };
            }
        }
        return result;
    }
    """)
    return rows


def calc_direction(open_odds, close_odds):
    """BM별 open/close 비교 → 홈 배당 방향 다수결"""
    home_ups, home_downs = 0, 0
    for bm in open_odds:
        if bm not in close_odds:
            continue
        h_open = open_odds[bm]['home']
        h_close = close_odds[bm]['home']
        if h_close > h_open:
            home_ups += 1
        elif h_close < h_open:
            home_downs += 1
    total = home_ups + home_downs
    if total == 0:
        return None, 0, 0
    home_dir = 1 if home_ups > home_downs else 0
    ratio = max(home_ups, home_downs) / total
    return home_dir, ratio, total


def main():
    today_str = _dt.today().strftime('%Y-%m-%d')
    mode = 'close' if IS_CLOSE else 'open'
    print(f'오늘 경기 배당 수집 [{mode}]: {today_str}')

    try:
        with open(TODAY_ODDS_PATH, encoding='utf-8') as f:
            today_odds = json.load(f)
    except:
        today_odds = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        matches = get_today_matches(page)
        print(f'오늘 경기 {len(matches)}개')

        for m in matches:
            key = f"{m['date']}|{int(m['slot'])}|{m['home']}|{m['away']}"
            print(f'\n[slot{int(m["slot"])}] {m["home"]} vs {m["away"]}')

            # close 수집 시 아침에 저장된 URL 우선 사용 (경기 시작 후 접근 불가 대비)
            entry = today_odds.get(key, {
                'date': m['date'], 'slot': m['slot'],
                'home': m['home'], 'away': m['away'],
            })
            scrape_url = entry.get('match_url', m['url'])

            bm_odds = scrape_bm_odds(page, scrape_url)
            print(f'  BM {len(bm_odds)}개 수집')

            if IS_CLOSE:
                entry['bm_close'] = bm_odds
                # 방향 계산
                open_odds = entry.get('bm_open', {})
                home_dir, ratio, count = calc_direction(open_odds, bm_odds)
                if home_dir is not None:
                    up_team   = m['home'] if home_dir == 1 else m['away']
                    down_team = m['away'] if home_dir == 1 else m['home']
                    entry['today_home_dir']   = home_dir
                    entry['today_dir_ratio']  = round(ratio, 3)
                    entry['today_dir_count']  = count
                    entry['today_up_team']    = up_team
                    entry['today_down_team']  = down_team
                    print(f'  홈배당 {"↑" if home_dir==1 else "↓"} | 배당↑={up_team}, 배당↓={down_team} ({ratio:.0%}, {count}BM)')
                else:
                    print('  방향 미확정 (open 미수집 or 변동 없음)')
            else:
                entry['bm_open'] = bm_odds
                entry['match_url'] = m['url']  # 아침 URL 저장 (close 수집 시 재사용)
                # close에서 overall 배당도 저장 (홈/원정 평균)
                if bm_odds:
                    h_avg = round(sum(v['home'] for v in bm_odds.values()) / len(bm_odds), 3)
                    a_avg = round(sum(v['away'] for v in bm_odds.values()) / len(bm_odds), 3)
                    entry['home_odds'] = h_avg
                    entry['away_odds'] = a_avg
                print(f'  open 저장 완료 ({len(bm_odds)}BM)')

            today_odds[key] = entry

        browser.close()

    with open(TODAY_ODDS_PATH, 'w', encoding='utf-8') as f:
        json.dump(today_odds, f, ensure_ascii=False, indent=2)
    print(f'\n저장 완료: {TODAY_ODDS_PATH}')

    if IS_CLOSE:
        print('\n=== 오늘 배당 방향 ===')
        for k, v in today_odds.items():
            if v.get('date') != today_str: continue
            d = v.get('today_home_dir')
            if d is not None:
                print(f"  {v['home']} vs {v['away']}: 배당↑={v['today_up_team']}, 배당↓={v['today_down_team']} ({v['today_dir_ratio']:.0%})")


if __name__ == '__main__':
    main()
