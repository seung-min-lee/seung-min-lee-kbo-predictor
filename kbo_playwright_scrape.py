"""
kbo_playwright_scrape.py
Playwright 기반 OddsPortal KBO open/close 배당 수집
CLICK_BMS: Cloudbet, GambleCity, Kobet, Melbet  (click → bg-gray-med_light 팝업)
HOVER_BMS: Momobet, Roobet, Stake.com, VOBET    (hover → z-30 absolute 툴팁)
"""
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pandas as pd
import time
from datetime import datetime as _dt, timedelta as _td

CSV_PATH  = 'kbo_odds.csv'
# 동적 날짜: 최근 LOOKBACK_DAYS 일 이내 open 미수집 경기 보충
LOOKBACK_DAYS = 30
_today    = _dt.today()
FILL_FROM = (_today - _td(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
FILL_TO   = (_today - _td(days=1)).strftime('%Y-%m-%d')

CLICK_BMS  = [                                                  # click → bg-gray-med_light 팝업
    '10x10bet', '1xBet', '22Bet', 'Alphabet', 'BetInAsia', 'Bets.io', 'bwin',
    'Cloudbet', 'GambleCity', 'Kobet', 'Melbet',
]
HOVER_BMS  = ['Momobet', 'Roobet', 'Stake.com', 'VOBET']     # hover → bg-gray-med absolute 팝업
POPUP_BMS  = CLICK_BMS + HOVER_BMS
NO_POPUP   = set()
EXCLUDE    = {'My coupon', 'User Predictions'}

# 팝업 초기화용 신뢰 BM (알파벳 앞 순)
INIT_BMS = ['1xBet', '22Bet', 'BetInAsia', 'Bets.io', 'Pinnacle', 'bet365', 'bwin', 'Betway']

# ─── 날짜 정규화 ───────────────────────────────────────────────────────────────
def normalize_date(raw):
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - _td(days=1)).strftime('%Y-%m-%d')
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s

# ─── 결과 페이지에서 match URL 수집 ───────────────────────────────────────────
JS_EXTRACT = """
() => {
    const results=[], seen=new Set();
    let currentDate='';
    document.querySelectorAll('div.eventRow').forEach(row=>{
        const dateEl=row.querySelector('[data-testid="date-header"]');
        if(dateEl&&dateEl.innerText.trim()) currentDate=dateEl.innerText.trim();
        const link=row.querySelector('a[href*="/h2h/"]');
        if(!link) return;
        const href=link.href;
        if(!href.includes('#')||seen.has(href)) return;
        seen.add(href);
        const teams=[...row.querySelectorAll('p.participant-name')]
            .map(el=>el.innerText.trim()).filter(Boolean).slice(0,2);
        const nums=[...row.querySelectorAll('[data-v-115522af]')]
            .map(el=>el.innerText.trim()).filter(t=>/^\\d+$/.test(t));
        const homeScore=parseInt(nums[0]);
        const awayScore=parseInt(nums[2]);
        const allText=row.innerText||'';
        const isPostp=!(!isNaN(homeScore)&&!isNaN(awayScore))&&/postp/i.test(allText);
        results.push({
            date:currentDate, url:href,
            match_id:href.split('#')[1],
            home:teams[0]||'', away:teams[1]||'',
            home_score:isPostp?null:(homeScore||0),
            away_score:isPostp?null:(awayScore||0),
            winner_is_home:isPostp?null:(homeScore>awayScore),
            finished:!isNaN(homeScore)&&!isNaN(awayScore)&&homeScore!==awayScore,
            postp:isPostp
        });
    });
    return results;
}
"""

def get_match_urls(page, stop_before=None):
    all_matches, seen_ids = [], set()
    for attempt in range(3):
        try:
            page.goto('https://www.oddsportal.com/baseball/south-korea/kbo/results/', timeout=60000)
            page.wait_for_selector('div.eventRow', timeout=30000)
            break
        except PWTimeout:
            print(f'  결과 페이지 로딩 실패 (attempt {attempt+1})')
            if attempt == 2:
                return []
            time.sleep(3)
    time.sleep(2)

    for pg in range(1, 15):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)
        print(f'  결과 페이지 {pg} 수집 중...')

        page_matches = page.evaluate(JS_EXTRACT)
        if not page_matches:
            print(f'  페이지 {pg} 데이터 없음 → 중단')
            break

        added, reached_stop = 0, False
        for m in page_matches:
            if m['match_id'] in seen_ids:
                continue
            seen_ids.add(m['match_id'])
            norm = normalize_date(m['date'])
            if stop_before and len(norm) == 10 and norm < stop_before:
                reached_stop = True
                continue
            all_matches.append(m)
            added += 1

        print(f'    → {added}개 추가 (누적 {len(all_matches)}개)')
        if reached_stop:
            print(f'  {stop_before} 이전 도달 → 완료')
            break

        # 다음 페이지 버튼 클릭
        went_next = page.evaluate("""
            () => {
                const cur = document.querySelector('a[data-number].active');
                if (!cur) return false;
                const curNum = parseInt(cur.getAttribute('data-number'));
                const next = [...document.querySelectorAll('a[data-number]')]
                    .find(b => parseInt(b.getAttribute('data-number')) === curNum + 1);
                if (next) { next.click(); return true; }
                return false;
            }
        """)
        if not went_next:
            print('  다음 페이지 없음 → 완료')
            break
        try:
            page.wait_for_selector('div.eventRow', timeout=10000)
            time.sleep(2)
        except PWTimeout:
            break

    # slot 계산 (날짜별 순번)
    date_counter = {}
    valid = []
    for m in all_matches:
        d = normalize_date(m['date'])
        date_counter[d] = date_counter.get(d, 0) + 1
        if date_counter[d] > 5:
            continue
        m['slot'] = date_counter[d]
        m['date'] = d
        valid.append(m)
    return valid


# ─── BM 팝업/hover → open/close 추출 ─────────────────────────────────────────
def _parse_popup_js(hover_only):
    """팝업/툴팁에서 open/close/change 추출하는 JS 코드 반환
    hover_only=True:  z-30 absolute 툴팁 (Momobet 등)
    hover_only=False: bg-gray-med_light 클릭 팝업 (Melbet 등)
    구조 공통: close(첫번째 font-bold 숫자) / open(mt-2 섹션 font-bold 숫자) / change(red/green)
    Array.from() 사용 — NodeList for..of 는 Playwright evaluate에서 오작동함
    """
    if hover_only:
        find_popup = """
            const allAbs = Array.from(document.querySelectorAll('div.height-content.absolute'));
            const popup = allAbs.find(el => el.className.includes('z-30'));
        """
    else:
        find_popup = """
            const allAbs = Array.from(document.querySelectorAll('div.height-content[class*="bg-gray-med_light"]'));
            const popup = allAbs.length ? allAbs[0] : null;
        """
    return f"""
        () => {{
            {find_popup}
            if (!popup) return null;

            // Close: DOM 순서상 첫 번째 숫자(>1) font-bold
            const boldArr = Array.from(popup.querySelectorAll('.font-bold'));
            const closeB  = boldArr.find(b => {{ const v = parseFloat(b.innerText); return !isNaN(v) && v > 1; }});
            const closeVal = closeB ? parseFloat(closeB.innerText) : null;

            // Open: mt-2 섹션의 첫 번째 숫자(>1) font-bold
            const mt2 = popup.querySelector('[class*="mt-2"]');
            let openVal = null;
            if (mt2) {{
                const mt2Arr = Array.from(mt2.querySelectorAll('.font-bold'));
                const openB  = mt2Arr.find(b => {{ const v = parseFloat(b.innerText); return !isNaN(v) && v > 1; }});
                openVal = openB ? parseFloat(openB.innerText) : null;
            }}

            const redEl   = popup.querySelector('[class*="text-red-dark"]');
            const greenEl = popup.querySelector('[class*="text-green-dark"]');
            const change  = redEl   ? redEl.innerText.trim()
                          : greenEl ? greenEl.innerText.trim() : null;

            return {{ openVal, closeVal, change }};
        }}
    """


def scrape_odds_popup(page, bm_name, side, hover_only=False):
    """
    hover_only=False: ElementHandle.click() → bg-gray-med_light 팝업 (Cloudbet, Melbet 등)
    hover_only=True : ElementHandle.hover() → z-30 absolute 툴팁 (Momobet, Roobet 등)
    ElementHandle API 사용 — page.evaluate(bbox)+mouse.move() 방식은 scroll 타이밍 문제로 툴팁 미표시
    """
    el_handle = page.evaluate_handle("""
        ([bm, side]) => {
            const nameEls = document.querySelectorAll('p.height-content.pl-4');
            for (const nel of nameEls) {
                if (nel.innerText.trim() !== bm) continue;
                let row = nel;
                for (let i = 0; i < 3; i++) row = row.parentElement;
                const oddsEls = row.querySelectorAll('p.odds-text');
                if (oddsEls.length < 2) return null;
                return side === 'home' ? oddsEls[0] : oddsEls[oddsEls.length - 1];
            }
            return null;
        }
    """, [bm_name, side])

    el = el_handle.as_element()
    if not el:
        return None

    try:
        el.scroll_into_view_if_needed()
        time.sleep(0.3)
        if hover_only:
            el.hover()
            time.sleep(1.5)
        else:
            el.hover()
            time.sleep(0.2)
            el.click()
            time.sleep(2.5)
    except Exception:
        return None

    data = page.evaluate(_parse_popup_js(hover_only))

    try:
        if hover_only:
            page.mouse.move(0, 0)
        else:
            page.keyboard.press('Escape')
        time.sleep(0.5)
    except Exception:
        pass

    return data


def popup_init(page, bm_map):
    """팝업 메커니즘 초기화: 신뢰 BM 중 하나를 클릭하고 ESC"""
    for ib in INIT_BMS:
        if ib not in bm_map:
            continue
        r = scrape_odds_popup(page, ib, 'home')
        if r is not None:
            print(f'  팝업 초기화 성공 ({ib})')
            return True
    # fallback: target BM이 아닌 아무 BM으로 시도
    for bm in bm_map:
        if bm in POPUP_BMS or bm in NO_POPUP or bm in EXCLUDE:
            continue
        r = scrape_odds_popup(page, bm, 'home')
        if r is not None:
            print(f'  팝업 초기화 성공 ({bm}) [fallback]')
            return True
    print('  팝업 초기화 실패')
    return False


def get_bm_list(page):
    """현재 페이지에 존재하는 BM 이름 목록 반환"""
    names = page.evaluate("""
        () => [...document.querySelectorAll('p.height-content.pl-4')]
              .map(el => el.innerText.trim())
              .filter(n => n)
    """)
    return [n for n in names if n not in EXCLUDE]


# ─── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    df = pd.read_csv(CSV_PATH)

    # 수집 대상 파악
    # 1) POPUP_BMS 인데 open 없는 기존 행
    popup_missing_ids = set(df[
        df['bookmaker'].isin(POPUP_BMS) &
        df['date'].between(FILL_FROM, FILL_TO) &
        df['home_open'].isna()
    ]['match_id'])

    # 2) Cloudbet 행 자체가 없는 경기 (기간 내)
    has_cloudbet = set(df[df['bookmaker'] == 'Cloudbet']['match_id'])
    all_mids_in_range = set(df[df['date'].between(FILL_FROM, FILL_TO)]['match_id'])
    cloudbet_missing_ids = all_mids_in_range - has_cloudbet

    target_ids = popup_missing_ids | cloudbet_missing_ids
    print(f'팝업 open 없는 경기: {len(popup_missing_ids)}개 match_id')
    print(f'Cloudbet 행 없는 경기: {len(cloudbet_missing_ids)}개 match_id')
    print(f'총 수집 대상: {len(target_ids)}개 match_id')

    if not target_ids:
        print('수집할 데이터 없음')
        return

    updated   = 0
    new_rows  = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1920,1080']
        )
        ctx = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1920, 'height': 1080}
        )
        page = ctx.new_page()

        print('\n경기 URL 수집 중...')
        match_list = get_match_urls(page, stop_before=FILL_FROM)
        target_matches = [m for m in match_list
                          if m['match_id'] in target_ids and m.get('finished')]
        print(f'URL 매칭: {len(target_matches)}경기\n')

        for idx, match in enumerate(target_matches):
            mid  = match['match_id']
            date = match['date']
            slot = match.get('slot', 0)
            home = match['home']
            away = match['away']
            print(f'[{idx+1}/{len(target_matches)}] {date} slot{slot}  {home} vs {away}')

            # 메타 정보 (기존 행 우선, 없으면 match_list에서)
            ref = df[df['match_id'] == mid]
            if not ref.empty:
                r              = ref.iloc[0]
                winner         = r['winner']
                winner_is_home = r['winner_is_home']
                home_score     = r['home_score']
                away_score     = r['away_score']
            else:
                wih            = match.get('winner_is_home')
                winner_is_home = wih
                winner         = home if wih else away
                home_score     = match.get('home_score')
                away_score     = match.get('away_score')

            # 경기 페이지 로드 (타임아웃/네트워크 오류 재시도)
            loaded = False
            for _attempt in range(3):
                try:
                    page.goto(match['url'], timeout=45000)
                    page.wait_for_selector('p.height-content.pl-4', timeout=15000)
                    loaded = True
                    break
                except Exception as _e:
                    print(f'  → 로딩 실패 (attempt {_attempt+1}): {type(_e).__name__}')
                    time.sleep(3)
            if not loaded:
                print('  → 3회 실패, 스킵')
                continue
            time.sleep(2)

            bm_list = get_bm_list(page)
            print(f'  BM 목록: {bm_list}')

            popup_init(page, {b: True for b in bm_list})

            for bm in POPUP_BMS:
                if bm not in bm_list:
                    continue

                mask = (df['match_id'] == mid) & (df['bookmaker'] == bm)
                if mask.any() and df.loc[mask, 'home_open'].notna().any():
                    continue  # 이미 open 있음

                ho = bm in HOVER_BMS
                h = scrape_odds_popup(page, bm, 'home', hover_only=ho)
                a = scrape_odds_popup(page, bm, 'away', hover_only=ho)

                h_open  = h['openVal']  if h else None
                h_close = h['closeVal'] if h else None
                a_open  = a['openVal']  if a else None
                a_close = a['closeVal'] if a else None

                h_chg = round(h_close - h_open, 4) if (h_open and h_close) else None
                a_chg = round(a_close - a_open, 4) if (a_open and a_close) else None
                odds_ratio = round(h_close / a_close, 4) if (h_close and a_close) else None
                consensus  = ('home' if odds_ratio and odds_ratio < 1
                              else ('away' if odds_ratio else None))

                print(f'  {bm}: h_open={h_open} h_close={h_close} | a_open={a_open} a_close={a_close}')

                h_dir = (1 if h_close > h_open else 0) if (h_open and h_close and h_open != h_close) else None
                a_dir = (1 if a_close > a_open else 0) if (a_open and a_close and a_open != a_close) else None
                w_dir = h_dir if winner_is_home else a_dir

                if mask.any():
                    if h_open:
                        df.loc[mask, ['home_open', 'home_close', 'home_change']] = [h_open, h_close, h_chg]
                        if h_dir is not None:
                            df.loc[mask, 'home_direction'] = h_dir
                    if a_open:
                        df.loc[mask, ['away_open', 'away_close', 'away_change']] = [a_open, a_close, a_chg]
                        if a_dir is not None:
                            df.loc[mask, 'away_direction'] = a_dir
                    if w_dir is not None:
                        df.loc[mask, 'winner_direction'] = w_dir
                    if h_open or a_open:
                        updated += 1
                else:
                    new_rows.append({
                        'match_id': mid, 'date': date, 'slot': slot,
                        'home': home, 'away': away,
                        'winner': winner, 'winner_is_home': winner_is_home,
                        'home_score': home_score, 'away_score': away_score,
                        'bookmaker': bm,
                        'home_open': h_open, 'home_close': h_close,
                        'home_change': h_chg, 'home_direction': h_dir,
                        'away_open': a_open, 'away_close': a_close,
                        'away_change': a_chg, 'away_direction': a_dir,
                        'winner_direction': w_dir,
                        'odds_ratio': odds_ratio, 'consensus': consensus,
                    })
                    updated += 1

                time.sleep(0.5)

            # 경기 단위 중간 저장 (크래시 대비)
            if updated > 0:
                _save_df = df if not new_rows else pd.concat(
                    [df, pd.DataFrame(new_rows)], ignore_index=True)
                _save_df = _save_df.sort_values(
                    ['date', 'slot', 'bookmaker']).reset_index(drop=True)
                _save_df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
                df = _save_df
                new_rows.clear()

            time.sleep(1)

        browser.close()

    # open/close 있는데 direction 없는 행 일괄 재계산
    df = pd.read_csv(CSV_PATH)
    has_h = df['home_open'].notna() & df['home_close'].notna()
    has_a = df['away_open'].notna() & df['away_close'].notna()
    miss_h = df['home_direction'].isna() & has_h
    miss_a = df['away_direction'].isna() & has_a
    miss_w = df['winner_direction'].isna()

    if miss_h.any():
        df.loc[miss_h, 'home_direction'] = (
            df.loc[miss_h, 'home_close'] > df.loc[miss_h, 'home_open']).astype(int)
    if miss_a.any():
        df.loc[miss_a, 'away_direction'] = (
            df.loc[miss_a, 'away_close'] > df.loc[miss_a, 'away_open']).astype(int)

    wih_true  = miss_w & (df['winner_is_home'] == True)  & has_h
    wih_false = miss_w & (df['winner_is_home'] == False) & has_a
    if wih_true.any():
        df.loc[wih_true, 'winner_direction'] = (
            df.loc[wih_true, 'home_close'] > df.loc[wih_true, 'home_open']).astype(int)
    if wih_false.any():
        df.loc[wih_false, 'winner_direction'] = (
            df.loc[wih_false, 'away_close'] > df.loc[wih_false, 'away_open']).astype(int)

    filled = int(miss_w.sum() - df['winner_direction'].isna().sum())
    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')

    if updated > 0 or filled > 0:
        print(f'\n완료: 업데이트 {updated}건, direction 재계산 {filled}건 → {CSV_PATH} 저장')
    else:
        print('\n업데이트 없음')


GAMES_PATH = 'kbo_games.csv'
GAMES_URL  = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

# OddsPortal 팀명 → 표준 팀명 매핑
TEAM_MAP = {
    'Doosan Bears':    'Doosan Bears',
    'Samsung Lions':   'Samsung Lions',
    'KIA Tigers':      'KIA Tigers',
    'LG Twins':        'LG Twins',
    'Kiwoom Heroes':   'Kiwoom Heroes',
    'SSG Landers':     'SSG Landers',
    'Lotte Giants':    'Lotte Giants',
    'NC Dinos':        'NC Dinos',
    'KT Wiz Suwon':    'KT Wiz Suwon',
    'Hanwha Eagles':   'Hanwha Eagles',
    # 혹시 약칭 사용 시
    'KT Wiz':          'KT Wiz Suwon',
}

JS_NEXT_MATCHES = """
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
        const mid = href.includes('#') ? href.split('#')[1]
                  : href.split('/').filter(Boolean).pop();
        // 현재 표시 배당 수집 (첫 번째 숫자 컬럼 = 평균 배당)
        const oddsEls = Array.from(row.querySelectorAll('p.odds-text, [data-testid="odds"]'))
            .map(el => parseFloat(el.innerText.trim())).filter(v => !isNaN(v) && v > 1);
        const home_odds = oddsEls.length >= 1 ? oddsEls[0] : null;
        const away_odds = oddsEls.length >= 2 ? oddsEls[oddsEls.length - 1] : null;
        results.push({date: currentDate, home: teams[0], away: teams[1], match_id: mid,
                      home_odds: home_odds, away_odds: away_odds});
    });
    return results;
}
"""

TODAY_ODDS_PATH = 'kbo_today_odds.json'

def get_next_matches(page):
    """OddsPortal KBO Next Matches 섹션에서 예정 경기 스크래핑"""
    for attempt in range(3):
        try:
            page.goto(GAMES_URL, timeout=60000)
            page.wait_for_selector('div.eventRow', timeout=30000)
            break
        except PWTimeout:
            print(f'  Next Matches 페이지 로딩 실패 (attempt {attempt+1})')
            if attempt == 2:
                return []
            time.sleep(3)
    time.sleep(2)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)

    raw = page.evaluate(JS_NEXT_MATCHES)
    print(f'  Raw 경기 {len(raw)}개 수집')

    today_str = _dt.today().strftime('%Y-%m-%d')
    seen_games = set()   # (date, home, away) 중복 제거
    results = []
    date_counter = {}
    for m in raw:
        norm = normalize_date(m['date'])
        if norm < today_str:
            continue

        home = TEAM_MAP.get(m['home'], m['home'])
        away = TEAM_MAP.get(m['away'], m['away'])
        key  = (norm, home, away)
        if key in seen_games:
            continue
        seen_games.add(key)

        date_counter[norm] = date_counter.get(norm, 0) + 1
        slot = date_counter[norm]
        if slot > 5:
            continue
        results.append({
            'date': norm, 'home': home, 'away': away,
            'away_score': None, 'home_score': None,
            'winner': None, 'winner_is_home': None,
            'slot': float(slot),
            'home_odds': m.get('home_odds'),
            'away_odds': m.get('away_odds'),
        })

    print(f'  필터 후 {len(results)}개 (오늘 이후)')

    # 오늘 개장 배당을 kbo_today_odds.json에 저장
    today_str = _dt.today().strftime('%Y-%m-%d')
    today_odds = {}
    for r in results:
        if r['date'] == today_str and r['home_odds'] and r['away_odds']:
            key = f"{r['date']}|{int(r['slot'])}|{r['home']}|{r['away']}"
            today_odds[key] = {
                'date': r['date'], 'slot': r['slot'],
                'home': r['home'], 'away': r['away'],
                'home_odds': r['home_odds'], 'away_odds': r['away_odds'],
            }
    if today_odds:
        import json as _json
        with open(TODAY_ODDS_PATH, 'w', encoding='utf-8') as f:
            _json.dump(today_odds, f, ensure_ascii=False, indent=2)
        print(f'  오늘 개장 배당 {len(today_odds)}경기 저장 → {TODAY_ODDS_PATH}')

    return results


def update_games_csv(next_matches):
    """kbo_games.csv에 새 예정 경기 추가 (중복 제외)"""
    if not next_matches:
        print('  추가할 경기 없음')
        return

    import os
    if os.path.exists(GAMES_PATH):
        gdf = pd.read_csv(GAMES_PATH)
    else:
        gdf = pd.DataFrame(columns=['date','away','home','away_score','home_score',
                                     'winner','winner_is_home','slot'])

    # 이미 있는 (date, slot) 쌍
    existing = set(zip(gdf['date'].astype(str), gdf['slot'].astype(str)))
    new_rows = []
    for m in next_matches:
        key = (str(m['date']), str(m['slot']))
        if key not in existing:
            new_rows.append({
                'date':           m['date'],
                'away':           m['away'],
                'home':           m['home'],
                'away_score':     None,
                'home_score':     None,
                'winner':         None,
                'winner_is_home': None,
                'slot':           m['slot'],
            })
            existing.add(key)

    if new_rows:
        gdf = pd.concat([gdf, pd.DataFrame(new_rows)], ignore_index=True)
        gdf = gdf.sort_values(['date', 'slot']).reset_index(drop=True)
        gdf.to_csv(GAMES_PATH, index=False, encoding='utf-8-sig')
        print(f'  {len(new_rows)}개 경기 추가 → {GAMES_PATH}')
    else:
        print('  신규 경기 없음 (이미 모두 등록)')


if __name__ == '__main__':
    # 1) Next Matches 먼저 업데이트
    print('\n=== Next Matches 스크래핑 ===')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
        page = browser.new_page(user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'))
        next_matches = get_next_matches(page)
        browser.close()
    update_games_csv(next_matches)

    # 2) 과거 배당 업데이트
    main()
