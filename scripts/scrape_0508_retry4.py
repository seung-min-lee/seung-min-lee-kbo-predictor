import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, statistics, re, pandas as pd, numpy as np
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGETS = [
    {'slot': 1.0, 'home': 'Doosan Bears',  'away': 'SSG Landers',  'match_id': 'dO3C2Hoo',
     'bms': ['Alphabet', 'GambleCity']},
    {'slot': 2.0, 'home': 'Hanwha Eagles', 'away': 'LG Twins',     'match_id': 'CC3GKG7T',
     'bms': ['bwin']},
    {'slot': 3.0, 'home': 'Lotte Giants',  'away': 'KIA Tigers',   'match_id': 'z78iQKwh',
     'bms': ['Kobet']},
]
DATE = '2026-05-08'
BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'


def load_page(page, url):
    for attempt in range(3):
        try:
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('p.height-content.pl-4', timeout=30000)
            time.sleep(5)
            return True
        except PWTimeout:
            if attempt == 2:
                return False
            time.sleep(5)
    return False


def try_click_popup(page, bm_name, side='home'):
    """BM 행에서 home 또는 away 셀을 찾아 클릭 후 팝업 파싱"""
    name_els = page.query_selector_all('p.height-content.pl-4')
    for nel in name_els:
        if nel.inner_text().strip() != bm_name:
            continue
        row = nel
        for _ in range(3):
            row = row.evaluate_handle('el => el.parentElement').as_element()
            if row is None:
                return None, None

        odds = row.query_selector_all('p.odds-text')
        if not odds:
            odds = row.query_selector_all('a.odds-link')
        if len(odds) < 2:
            return None, None

        target = odds[0] if side == 'home' else odds[-1]
        try:
            target.scroll_into_view_if_needed()
            time.sleep(0.3)
            target.click(force=True)
            time.sleep(2)
        except Exception as e:
            print(f'    click 오류: {e}')
            return None, None

        popup = page.query_selector("div[class*='fixed'][class*='height-content']")
        if not popup:
            # 대체 셀렉터 시도
            popup = page.query_selector("div.height-content[class*='bg-gray']")
        if not popup:
            return None, None

        text = popup.inner_text()
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)
        cm = re.search(r'Odds movement:[\s\S]*?([\d.]{3,})', text)
        page.keyboard.press('Escape')
        time.sleep(0.5)

        if om and cm:
            return float(om.group(1)), float(cm.group(1))
        return None, None
    return None, None


def scrape_bm_open(page, url, bm_name):
    """3회 시도 → median"""
    h_opens, h_closes, a_opens, a_closes = [], [], [], []
    for attempt in range(3):
        if not load_page(page, url):
            break
        h_o, h_c = try_click_popup(page, bm_name, 'home')
        a_o, a_c = try_click_popup(page, bm_name, 'away')
        print(f'    attempt{attempt+1}: h_open={h_o}, a_open={a_o}')
        if h_o: h_opens.append(h_o); h_closes.append(h_c)
        if a_o: a_opens.append(a_o); a_closes.append(a_c)

    result = {}
    if h_opens:
        result['home_open'] = statistics.median(h_opens)
        result['home_close_popup'] = statistics.median(h_closes)
        if len(h_opens) > 1 and max(h_opens) - min(h_opens) > 0.05:
            print(f'    ⚠ home_open 편차: {h_opens}')
    if a_opens:
        result['away_open'] = statistics.median(a_opens)
        if len(a_opens) > 1 and max(a_opens) - min(a_opens) > 0.05:
            print(f'    ⚠ away_open 편차: {a_opens}')
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

    for g in TARGETS:
        home_slug = g['home'].lower().replace(' ', '-')
        away_slug = g['away'].lower().replace(' ', '-')
        url = f"{BASE}{home_slug}-{away_slug}-{g['match_id']}/"
        print(f"\n[slot{int(g['slot'])}] {g['home']} vs {g['away']}")

        mask = (df['date'] == DATE) & (df['slot'] == g['slot'])
        for bm in g['bms']:
            print(f"  BM: {bm}")
            pop = scrape_bm_open(page, url, bm)
            if pop:
                bm_mask = mask & (df['bookmaker'] == bm)
                if 'home_open' in pop:
                    df.loc[bm_mask, 'home_open'] = pop['home_open']
                    print(f"  → home_open={pop['home_open']}")
                if 'away_open' in pop:
                    df.loc[bm_mask, 'away_open'] = pop['away_open']
                    print(f"  → away_open={pop['away_open']}")
            else:
                print(f"  → 실패")

    browser.close()

mask08 = df['date'] == DATE
df.loc[mask08, 'home_change'] = (df.loc[mask08, 'home_close'] - df.loc[mask08, 'home_open']).round(3)
df.loc[mask08, 'away_change'] = (df.loc[mask08, 'away_close'] - df.loc[mask08, 'away_open']).round(3)
df.loc[mask08, 'winner_direction'] = df[mask08].apply(calc_dir, axis=1)

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 저장 완료 ===')
nan_h = df[mask08]['home_open'].isna().sum()
nan_wd = df[mask08]['winner_direction'].isna().sum()
print(f'home_open NaN: {nan_h}/70')
print(f'winner_direction NaN: {nan_wd}/70')
print()
print(df[mask08 & df['bookmaker'].isin(['Alphabet','GambleCity','bwin','Kobet'])][
    ['slot','bookmaker','home_open','home_close','away_open','away_close','winner_direction']
].to_string())
