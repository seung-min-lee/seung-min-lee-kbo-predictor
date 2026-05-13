"""
05-12 kbo_odds.csv home_open / home_direction / winner_direction 재수집
Playwright popup 클릭 방식으로 openVal/closeVal 추출, kbo_odds.csv 업데이트
"""
import os as _os; _os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import time, tempfile
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGET_DATE      = '2026-05-12'
CSV_PATH         = 'kbo_odds.csv'
GAMES_PATH       = 'kbo_games.csv'
RESULTS_URL      = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
EXCLUDE          = {'My coupon', 'User Predictions', 'Betfair Exchange'}
TARGET_MATCH_IDS = {'ELRyShWg', 'YNswQW06', 't8TTTE1s', 'fHfBBXoD', 'MNncZzvK'}

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
    for attempt in range(2):
        try:
            el_handle.scroll_into_view_if_needed()
            time.sleep(0.3)
            el_handle.hover()
            time.sleep(0.3)
            el_handle.click()
        except Exception:
            return None
        try:
            page.wait_for_selector(
                'div.height-content[class*="bg-gray-med_light"], div[class*="fixed"][class*="height-content"]',
                timeout=3000
            )
        except PWTimeout:
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


def get_match_urls(page):
    """결과 페이지(최대 3페이지)에서 target match_id URL 수집"""
    urls = {}
    for attempt in range(3):
        try:
            page.goto(RESULTS_URL, timeout=90000, wait_until='domcontentloaded')
            page.wait_for_selector('div.eventRow', timeout=45000)
            break
        except PWTimeout:
            if attempt == 2: return urls
            time.sleep(5)

    for pg in range(1, 4):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)
        for mid in list(TARGET_MATCH_IDS):
            if mid in urls:
                continue
            link = page.query_selector(f'a[href*="#{mid}"]')
            if link:
                href = link.get_attribute('href')
                if href and href.startswith('/'):
                    href = 'https://www.oddsportal.com' + href
                urls[mid] = href
        print(f'  결과 페이지 {pg}: {len(urls)}/{len(TARGET_MATCH_IDS)}개 URL 수집')
        if len(urls) == len(TARGET_MATCH_IDS):
            break

        next_num = page.evaluate("""
            const cur = document.querySelector('a[data-number].active');
            if (!cur) return null;
            const curNum = parseInt(cur.getAttribute('data-number'));
            const btns = [...document.querySelectorAll('a[data-number]')];
            const nb = btns.find(b => parseInt(b.getAttribute('data-number')) === curNum + 1);
            return nb ? nb.getAttribute('data-number') : null;
        """)
        if not next_num:
            break
        page.evaluate(f"""
            const btns = [...document.querySelectorAll('a[data-number]')];
            const nb = btns.find(b => b.getAttribute('data-number') === '{next_num}');
            if (nb) nb.click();
        """)
        time.sleep(3)
        try:
            page.wait_for_selector('div.eventRow', timeout=15000)
        except PWTimeout:
            break

    return urls


def scrape_match_odds(page, url):
    """경기 페이지에서 BM별 openVal/closeVal 수집"""
    for attempt in range(2):
        try:
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('p.height-content.pl-4', timeout=30000)
            break
        except Exception:
            if attempt == 1:
                print('    로딩 실패')
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
                'home_close': home_data.get('closeVal') or home_data.get('openVal'),
                'away_close': away_data.get('closeVal') or away_data.get('openVal'),
            }
    return result


def _atomic_csv(path, df):
    dir_ = _os.path.dirname(_os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.tmp')
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as f:
            df.to_csv(f, index=False)
        _os.replace(tmp, path)
    except Exception:
        _os.unlink(tmp)
        raise


def main():
    print(f'05-12 BM 재수집 시작')

    df    = pd.read_csv(CSV_PATH)
    games = pd.read_csv(GAMES_PATH)

    wih_map = {}
    for _, g in games[games['date'] == TARGET_DATE].iterrows():
        wih_map[(g['home'], g['away'])] = bool(g['winner_is_home'])

    print(f'winner_is_home 매핑: {wih_map}')

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

        page = _new_page()
        match_urls = get_match_urls(page)
        page.context.close()

        print(f'\nURL 수집 결과:')
        for mid, url in match_urls.items():
            print(f'  {mid}: {url}')
        missing = TARGET_MATCH_IDS - set(match_urls.keys())
        if missing:
            print(f'  미수집: {missing}')

        for mid in TARGET_MATCH_IDS:
            if mid not in match_urls:
                print(f'\n[{mid}] URL 없음 → 스킵')
                continue

            rows_mask = df['match_id'] == mid
            if not rows_mask.any():
                print(f'\n[{mid}] kbo_odds.csv에 없음 → 스킵')
                continue

            home = df.loc[rows_mask, 'home'].iloc[0]
            away = df.loc[rows_mask, 'away'].iloc[0]
            winner_is_home = wih_map.get((home, away))

            print(f'\n[{mid}] {home} vs {away} (winner_is_home={winner_is_home})')

            slot_page = _new_page()
            try:
                bm_data = scrape_match_odds(slot_page, match_urls[mid])
            except Exception as e:
                print(f'  오류: {e}')
                bm_data = {}
            finally:
                slot_page.context.close()

            print(f'  BM {len(bm_data)}개 수집')
            if not bm_data:
                continue

            updated = 0
            for bm, v in bm_data.items():
                mask = rows_mask & (df['bookmaker'] == bm)
                if not mask.any():
                    continue

                home_open  = v.get('home_open')
                away_open  = v.get('away_open')
                home_close = v.get('home_close')
                away_close = v.get('away_close')

                home_dir = None
                away_dir = None
                if home_open and home_close and abs(home_close - home_open) > 0.005:
                    home_dir = 1 if home_close > home_open else 0
                if away_open and away_close and abs(away_close - away_open) > 0.005:
                    away_dir = 1 if away_close > away_open else 0

                winner_dir = None
                if winner_is_home is not None:
                    cand = home_dir if winner_is_home else away_dir
                    if home_dir is not None and away_dir is not None and home_dir == away_dir:
                        winner_dir = None  # N 조건
                    else:
                        winner_dir = cand

                if home_open  is not None: df.loc[mask, 'home_open']        = home_open
                if away_open  is not None: df.loc[mask, 'away_open']        = away_open
                if home_close is not None: df.loc[mask, 'home_close']       = home_close
                if away_close is not None: df.loc[mask, 'away_close']       = away_close
                if home_dir   is not None: df.loc[mask, 'home_direction']   = home_dir
                if away_dir   is not None: df.loc[mask, 'away_direction']   = away_dir
                if winner_dir is not None: df.loc[mask, 'winner_direction'] = winner_dir
                updated += 1

            print(f'  → {updated}개 북메이커 업데이트')

        browser.close()

    _atomic_csv(CSV_PATH, df)

    m12 = df[df['date'] == TARGET_DATE]
    print(f'\n05-12 최종 결과:')
    print(f'  행 수: {len(m12)}')
    print(f'  home_open 수집:        {m12["home_open"].notna().sum()}/{len(m12)}')
    print(f'  home_direction 수집:   {m12["home_direction"].notna().sum()}/{len(m12)}')
    print(f'  winner_direction 수집: {m12["winner_direction"].notna().sum()}/{len(m12)}')


if __name__ == '__main__':
    main()
