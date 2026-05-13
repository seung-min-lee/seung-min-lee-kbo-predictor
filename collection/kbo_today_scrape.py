"""
오늘 예정 경기 BM별 배당 수집 → kbo_today_odds.json에 저장

팝업 클릭 방식으로 OddsPortal Opening odds / Closing odds 수집:
  - bm_open  : Opening odds (팝업의 openVal)
  - bm_close : Closing odds (팝업의 closeVal = Opening + Odds movement)

사용: python kbo_today_scrape.py [--close] [--no-h2h]
  --close  없으면: Opening odds → bm_open 저장 (closeVal=openVal이면 bm_close 미저장)
  --close  있으면: Closing odds → bm_close 저장 + today_home_dir 계산
  --no-h2h 있으면: h2h 링크 사용 안 함 (/kbo/ 직접 링크만 허용)
"""
import os as _os; _os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys, json, time
from datetime import datetime as _dt
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TODAY_ODDS_PATH = 'kbo_today_odds.json'
GAMES_URL       = 'https://www.oddsportal.com/baseball/south-korea/kbo/'
EXCLUDE         = {'My coupon', 'User Predictions', 'Betfair Exchange'}
IS_CLOSE        = '--close' in sys.argv
ALLOW_H2H       = '--no-h2h' not in sys.argv

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

    allow_h2h_js = 'true' if ALLOW_H2H else 'false'
    raw = page.evaluate("""
    () => {
        const ALLOW_H2H = __ALLOW_H2H__;
        const results = [], seen = new Set();
        let currentDate = '';
        document.querySelectorAll('div.eventRow').forEach(row => {
            const dateEl = row.querySelector('[data-testid="date-header"]');
            if (dateEl && dateEl.innerText.trim()) currentDate = dateEl.innerText.trim();
            // h2h 경기별 링크 우선(ALLOW_H2H=true), 없으면 /kbo/ match slug 링크 사용 (breadcrumb 제외)
            let link = ALLOW_H2H ? row.querySelector('a[href*="/h2h/"]') : null;
            if (!link) {
                const kboLinks = Array.from(row.querySelectorAll('a[href*="/kbo/"]'))
                    .filter(a => a.href.split('/kbo/')[1] && a.href.split('/kbo/')[1].length > 5);
                if (kboLinks.length) link = kboLinks[0];
            }
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
    """.replace('__ALLOW_H2H__', allow_h2h_js))

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


POPUP_JS = """
() => {
    const popup = document.querySelector('div.height-content[class*="bg-gray-med_light"]')
               || document.querySelector('div[class*="fixed"][class*="height-content"]');
    if (!popup) return null;
    let openVal = null, closeVal = null;
    const openSection = popup.querySelector('div[class*="mt-2"]');
    if (openSection) {
        const boldEls = openSection.querySelectorAll('.font-bold');
        for (let i = 0; i < boldEls.length; i++) {
            const v = parseFloat(boldEls[i].innerText);
            if (!isNaN(v) && v > 1) { openVal = v; break; }
        }
    }
    const rowDiv = popup.querySelector('.flex.flex-row');
    if (rowDiv) {
        const cols = rowDiv.querySelectorAll(':scope > div');
        if (cols.length > 1) {
            const boldEl = cols[1].querySelector('.font-bold');
            if (boldEl) {
                const v = parseFloat(boldEl.innerText);
                if (!isNaN(v) && v > 1) closeVal = v;
            }
        }
    }
    return { openVal, closeVal };
}
"""

def _popup_odds(page, el_handle):
    """odds 셀 클릭 → 팝업에서 openVal/closeVal 추출 (최대 2회 재시도)"""
    for attempt in range(2):
        try:
            el_handle.scroll_into_view_if_needed()
            time.sleep(0.3)
            el_handle.hover()
            time.sleep(0.3)
            el_handle.click()
        except Exception:
            return None
        # 팝업 명시적 대기
        try:
            page.wait_for_selector(
                'div.height-content[class*="bg-gray-med_light"], div[class*="fixed"][class*="height-content"]',
                timeout=3000
            )
        except PWTimeout:
            # 팝업 안 열렸으면 Escape 후 재시도
            try:
                page.keyboard.press('Escape')
                time.sleep(0.5)
            except Exception:
                pass
            if attempt == 1:
                return None
            continue
        data = page.evaluate(POPUP_JS)
        try:
            page.keyboard.press('Escape')
            time.sleep(0.3)
        except Exception:
            pass
        if data and (data.get('openVal') or data.get('closeVal')):
            return data
    return None


def scrape_bm_odds(page, url):
    """경기 페이지에서 BM별 Opening/Closing odds 수집 (팝업 클릭 방식)
    반환: {bm: {home_open, away_open, home_close, away_close}}
    """
    for attempt in range(2):
        try:
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('p.height-content.pl-4', timeout=30000)
            break
        except Exception:
            if attempt == 1:
                print('  로딩 실패')
                return {}
            time.sleep(5)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)
    page.evaluate('window.scrollTo(0, 0)')
    time.sleep(1)

    result = {}
    bm_els = page.query_selector_all('p.height-content.pl-4')
    for bm_el in bm_els:
        bm = bm_el.inner_text().strip()
        if not bm or bm in EXCLUDE:
            continue

        row_handle = bm_el.evaluate_handle(
            'el => { let r = el; for (let i=0;i<3;i++) r=r.parentElement; return r; }'
        ).as_element()
        if not row_handle:
            continue

        odds_els = row_handle.query_selector_all('a.odds-link')
        if not odds_els:
            odds_els = row_handle.query_selector_all('p.odds-text')
        if len(odds_els) < 2:
            continue

        home_data = _popup_odds(page, odds_els[0])
        away_data = _popup_odds(page, odds_els[-1])

        if home_data and away_data:
            result[bm] = {
                'home_open':  home_data.get('openVal'),
                'away_open':  away_data.get('openVal'),
                'home_close': home_data.get('closeVal'),
                'away_close': away_data.get('closeVal'),
            }

    return result


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

        def _new_page():
            ctx = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            p = ctx.new_page()
            p.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            return p

        # 경기 목록 수집
        page = _new_page()
        matches = get_today_matches(page)
        page.context.close()
        print(f'오늘 경기 {len(matches)}개')

        for m in matches:
            key = f"{m['date']}|{int(m['slot'])}|{m['home']}|{m['away']}"
            print(f'\n[slot{int(m["slot"])}] {m["home"]} vs {m["away"]}')

            # close 수집 시 슬롯 번호 달라도 팀명으로 기존 open 키 찾기
            if IS_CLOSE and key not in today_odds:
                matched_key = next(
                    (k for k in today_odds
                     if today_odds[k].get('home') == m['home']
                     and today_odds[k].get('away') == m['away']
                     and today_odds[k].get('date') == m['date']),
                    None
                )
                if matched_key:
                    key = matched_key

            # close 수집 시 아침에 저장된 URL 우선 사용 (경기 시작 후 접근 불가 대비)
            entry = today_odds.get(key, {
                'date': m['date'], 'slot': m['slot'],
                'home': m['home'], 'away': m['away'],
            })
            scrape_url = entry.get('match_url', m['url'])

            # 슬롯마다 새 컨텍스트 (소켓 끊김 방지)
            slot_page = _new_page()
            try:
                bm_data = scrape_bm_odds(slot_page, scrape_url)
            except Exception as e:
                print(f'  수집 오류: {e}')
                bm_data = {}
            finally:
                slot_page.context.close()
            print(f'  BM {len(bm_data)}개 수집')

            if not bm_data:
                today_odds[key] = entry
                continue

            # Opening odds → bm_open (항상 덮어쓰기, 변하지 않는 값)
            bm_open = {bm: {'home': v['home_open'], 'away': v['away_open']}
                       for bm, v in bm_data.items()
                       if v.get('home_open') and v.get('away_open')}
            if bm_open:
                entry['bm_open'] = bm_open
                entry['match_url'] = m['url']
                h_avg = round(sum(v['home'] for v in bm_open.values()) / len(bm_open), 3)
                a_avg = round(sum(v['away'] for v in bm_open.values()) / len(bm_open), 3)
                entry['home_odds'] = h_avg
                entry['away_odds'] = a_avg

            # Closing odds → bm_close (closeVal이 openVal과 다를 때만 저장)
            bm_close = {bm: {'home': v['home_close'], 'away': v['away_close']}
                        for bm, v in bm_data.items()
                        if v.get('home_close') and v.get('away_close')
                        and v['home_close'] != v['home_open']}
            if bm_close:
                entry['bm_close'] = bm_close
                # close 기준 home_odds/away_odds 업데이트
                h_avg = round(sum(v['home'] for v in bm_close.values()) / len(bm_close), 3)
                a_avg = round(sum(v['away'] for v in bm_close.values()) / len(bm_close), 3)
                entry['home_odds'] = h_avg
                entry['away_odds'] = a_avg

            if IS_CLOSE:
                # 방향 계산: bm_open vs bm_close
                open_odds  = entry.get('bm_open', {})
                close_odds = entry.get('bm_close', {})
                home_dir, ratio, count = calc_direction(open_odds, close_odds)
                if home_dir is not None:
                    up_team   = m['home'] if home_dir == 1 else m['away']
                    down_team = m['away'] if home_dir == 1 else m['home']
                    entry['today_home_dir']  = home_dir
                    entry['today_dir_ratio'] = round(ratio, 3)
                    entry['today_dir_count'] = count
                    entry['today_up_team']   = up_team
                    entry['today_down_team'] = down_team
                    print(f'  홈배당 {"↑" if home_dir==1 else "↓"} | 배당↑={up_team}, 배당↓={down_team} ({ratio:.0%}, {count}BM)')
                else:
                    print('  방향 미확정 (변동 없음)')
            else:
                print(f'  open 저장 완료 (open:{len(bm_open)}BM, close변동:{len(bm_close)}BM)')

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
