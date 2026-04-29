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

CLICK_BMS  = ['Cloudbet', 'GambleCity', 'Kobet', 'Melbet']    # click → bg-gray-med_light 팝업
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

            # 경기 페이지 로드
            try:
                page.goto(match['url'], timeout=45000)
                page.wait_for_selector('p.height-content.pl-4', timeout=15000)
            except PWTimeout:
                print('  → 페이지 로딩 실패, 스킵')
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

                if mask.any():
                    if h_open:
                        df.loc[mask, ['home_open', 'home_close', 'home_change']] = [h_open, h_close, h_chg]
                    if a_open:
                        df.loc[mask, ['away_open', 'away_close', 'away_change']] = [a_open, a_close, a_chg]
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
                        'home_change': h_chg, 'home_direction': None,
                        'away_open': a_open, 'away_close': a_close,
                        'away_change': a_chg, 'away_direction': None,
                        'winner_direction': None,
                        'odds_ratio': odds_ratio, 'consensus': consensus,
                    })
                    updated += 1

                time.sleep(0.5)

            time.sleep(1)

        browser.close()

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df = df.sort_values(['date', 'slot', 'bookmaker']).reset_index(drop=True)

    if updated > 0:
        df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
        print(f'\n완료: 업데이트 {updated}건, 신규행 {len(new_rows)}개 → {CSV_PATH} 저장')
    else:
        print('\n업데이트 없음')


if __name__ == '__main__':
    main()
