import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, statistics, re, pandas as pd, numpy as np
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

GAMES = [
    {'slot': 1.0, 'home': 'Doosan Bears',  'away': 'SSG Landers',   'match_id': 'dO3C2Hoo'},
    {'slot': 2.0, 'home': 'Hanwha Eagles', 'away': 'LG Twins',      'match_id': 'CC3GKG7T'},
    {'slot': 3.0, 'home': 'Lotte Giants',  'away': 'KIA Tigers',    'match_id': 'z78iQKwh'},
    {'slot': 4.0, 'home': 'Kiwoom Heroes', 'away': 'KT Wiz Suwon',  'match_id': '4n08MxwH'},
    {'slot': 5.0, 'home': 'NC Dinos',      'away': 'Samsung Lions', 'match_id': 'rXBaOb84'},
]
DATE = '2026-05-08'
BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'
EXCLUDE = {'My coupon', 'User Predictions', 'Betfair Exchange'}


def load_page(page, url):
    for attempt in range(3):
        try:
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('p.height-content.pl-4', timeout=30000)
            time.sleep(4)
            return True
        except PWTimeout:
            if attempt == 2:
                return False
            time.sleep(5)
    return False


def scrape_close(page, url):
    if not load_page(page, url):
        return {}
    return page.evaluate("""
    () => {
        const EXCLUDE = new Set(["My coupon","User Predictions","Betfair Exchange"]);
        const result = {};
        for (const nel of document.querySelectorAll("p.height-content.pl-4")) {
            const bm = nel.innerText.trim();
            if (!bm || EXCLUDE.has(bm)) continue;
            let row = nel;
            for (let i=0; i<3; i++) row = row.parentElement;
            let els = Array.from(row.querySelectorAll("a.odds-link"));
            if (!els.length) els = Array.from(row.querySelectorAll("p.odds-text"));
            if (els.length < 2) continue;
            const h = parseFloat(els[0].innerText.trim());
            const a = parseFloat(els[els.length-1].innerText.trim());
            if (!isNaN(h) && h>1 && !isNaN(a) && a>1) result[bm] = {home:h, away:a};
        }
        return result;
    }
    """)


def get_bm_row_odds_handles(page, bm_name):
    """BM 이름으로 해당 행의 홈/원정 odds 엘리먼트 핸들 반환"""
    name_els = page.query_selector_all('p.height-content.pl-4')
    for nel in name_els:
        if nel.inner_text().strip() != bm_name:
            continue
        # 부모 3단계 위로
        row = nel
        for _ in range(3):
            row = row.evaluate_handle('el => el.parentElement')
            row = row.as_element()
            if row is None:
                return None, None
        # odds-text 또는 odds-link
        odds = row.query_selector_all('p.odds-text')
        if not odds:
            odds = row.query_selector_all('a.odds-link')
        if len(odds) >= 2:
            return odds[0], odds[-1]
    return None, None


def read_popup(page):
    """팝업 텍스트에서 open/close 값 파싱"""
    popup = page.query_selector("div[class*='fixed'][class*='height-content']")
    if not popup:
        return None, None
    text = popup.inner_text()
    om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)
    cm = re.search(r'Odds movement:[\s\S]*?([\d.]{3,})', text)
    if om and cm:
        return float(om.group(1)), float(cm.group(1))
    return None, None


def close_popup(page):
    page.keyboard.press('Escape')
    time.sleep(0.3)


def scrape_open_3times(page, url, bm_name):
    """3회 팝업 클릭으로 home_open, away_open 수집 → median"""
    h_opens, h_closes = [], []
    a_opens, a_closes = [], []

    for attempt in range(3):
        if not load_page(page, url):
            break
        h_el, a_el = get_bm_row_odds_handles(page, bm_name)

        if h_el is None:
            print(f'      {bm_name}: 행 탐색 실패')
            break

        # home 팝업
        try:
            h_el.scroll_into_view_if_needed()
            h_el.click()
            time.sleep(1.5)
            h_open, h_close = read_popup(page)
            if h_open:
                h_opens.append(h_open)
                h_closes.append(h_close)
            close_popup(page)
        except Exception as e:
            print(f'      home 클릭 오류: {e}')
            close_popup(page)

        # away 팝업
        try:
            a_el.scroll_into_view_if_needed()
            a_el.click()
            time.sleep(1.5)
            a_open, a_close = read_popup(page)
            if a_open:
                a_opens.append(a_open)
                a_closes.append(a_close)
            close_popup(page)
        except Exception as e:
            print(f'      away 클릭 오류: {e}')
            close_popup(page)

    result = {}
    if h_opens:
        result['home_open'] = statistics.median(h_opens)
        result['home_close_popup'] = statistics.median(h_closes)
        if len(h_opens) > 1 and max(h_opens) - min(h_opens) > 0.05:
            print(f'      ⚠ {bm_name} home_open 편차: {h_opens}')
    if a_opens:
        result['away_open'] = statistics.median(a_opens)
        result['away_close_popup'] = statistics.median(a_closes)
        if len(a_opens) > 1 and max(a_opens) - min(a_opens) > 0.05:
            print(f'      ⚠ {bm_name} away_open 편차: {a_opens}')
    return result


def calc_dir(row):
    if pd.isna(row['home_open']) or pd.isna(row['away_open']):
        return np.nan
    if pd.isna(row['winner_is_home']):
        return np.nan
    h_chg = row['home_close'] - row['home_open']
    a_chg = row['away_close'] - row['away_open']
    w_chg = h_chg if row['winner_is_home'] else a_chg
    l_chg = a_chg if row['winner_is_home'] else h_chg
    if abs(w_chg - l_chg) < 0.001:
        return np.nan
    return 1.0 if w_chg > l_chg else 0.0


df = pd.read_csv('kbo_odds.csv')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

    for g in GAMES:
        home_slug = g['home'].lower().replace(' ', '-')
        away_slug = g['away'].lower().replace(' ', '-')
        url = f"{BASE}{home_slug}-{away_slug}-{g['match_id']}/"
        print(f"\n[slot{int(g['slot'])}] {g['home']} vs {g['away']}")

        # Step 1: 3회 close 수집 → 중앙값
        all_runs = []
        for run in range(3):
            data = scrape_close(page, url)
            all_runs.append(data)
            print(f"  close run{run+1}: {len(data)}BM")
            if run < 2:
                time.sleep(3)

        all_bms = set()
        for r in all_runs:
            all_bms.update(r.keys())

        close_medians = {}
        for bm in all_bms:
            vals_h = [r[bm]['home'] for r in all_runs if bm in r]
            vals_a = [r[bm]['away'] for r in all_runs if bm in r]
            if len(vals_h) >= 2:
                mh = statistics.median(vals_h)
                ma = statistics.median(vals_a)
                if max(vals_h) - min(vals_h) > 0.05:
                    print(f"  ⚠ {bm} home_close 편차: {vals_h}")
                close_medians[bm] = {'home': mh, 'away': ma}

        print(f"  close 확정: {len(close_medians)}BM")

        # Step 2: BM별 open 팝업 수집 (3회)
        open_results = {}
        for bm in sorted(close_medians.keys()):
            pop = scrape_open_3times(page, url, bm)
            open_results[bm] = pop
            if pop:
                ho = pop.get('home_open', '?')
                ao = pop.get('away_open', '?')
                print(f"  {bm}: h_open={ho}, a_open={ao}")
            else:
                print(f"  {bm}: open 수집 실패")

        # Step 3: kbo_odds.csv 업데이트
        mask = (df['date'] == DATE) & (df['slot'] == g['slot'])
        for bm, v in close_medians.items():
            bm_mask = mask & (df['bookmaker'] == bm)
            if bm_mask.any():
                df.loc[bm_mask, 'home_close'] = v['home']
                df.loc[bm_mask, 'away_close'] = v['away']

        for bm, v in open_results.items():
            bm_mask = mask & (df['bookmaker'] == bm)
            if not bm_mask.any() or not v:
                continue
            if 'home_open' in v:
                df.loc[bm_mask, 'home_open'] = v['home_open']
            if 'away_open' in v:
                df.loc[bm_mask, 'away_open'] = v['away_open']

    browser.close()

# 재계산
mask08 = df['date'] == DATE
df.loc[mask08, 'home_change'] = (df.loc[mask08, 'home_close'] - df.loc[mask08, 'home_open']).round(3)
df.loc[mask08, 'away_change'] = (df.loc[mask08, 'away_close'] - df.loc[mask08, 'away_open']).round(3)
df.loc[mask08, 'winner_direction'] = df[mask08].apply(calc_dir, axis=1)

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 저장 완료 ===')
print(df[mask08].groupby(['home', 'away'])['winner_direction'].value_counts(dropna=False).to_string())

# NaN 현황
print('\n=== NaN 현황 ===')
for col in ['home_open', 'away_open', 'home_change', 'winner_direction']:
    n = df[mask08][col].isna().sum()
    print(f'  {col}: NaN {n}/{mask08.sum()}')
