import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, statistics, re, pandas as pd, numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

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
EXCLUDE = {'My coupon', 'User Predictions', 'Betfair Exchange'}


def make_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def load_page(driver, url):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
        return True
    except:
        return False


def get_popup_values(driver, bm_name, side='home'):
    """BM 행에서 해당 셀 클릭 → 팝업 open/close 파싱"""
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target_nel = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target_nel = nel
                break
        if target_nel is None:
            return None, None

        row = target_nel
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None, None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        driver.execute_script("window.scrollBy(0,-100);")
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", el)
        time.sleep(2)

        popup = driver.execute_script("""
            return document.querySelector('div[class*="fixed"][class*="height-content"]');
        """)
        if not popup:
            popup = driver.execute_script("""
                return document.querySelector('div.height-content[class*="bg-gray"]');
            """)
        if not popup:
            return None, None

        text = driver.execute_script("return arguments[0].innerText;", popup)
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)
        cm = re.search(r'Odds movement:[\s\S]*?([\d.]{3,})', text)

        # 팝업 닫기
        driver.execute_script("arguments[0].click();", el)
        time.sleep(0.5)

        if om and cm:
            return float(om.group(1)), float(cm.group(1))
        return None, None
    except Exception as e:
        print(f'    오류: {e}')
        return None, None


def scrape_3times(driver, url, bm_name):
    h_opens, a_opens = [], []
    for attempt in range(3):
        if not load_page(driver, url):
            break
        h_o, _ = get_popup_values(driver, bm_name, 'home')
        a_o, _ = get_popup_values(driver, bm_name, 'away')
        print(f'    attempt{attempt+1}: h_open={h_o}, a_open={a_o}')
        if h_o: h_opens.append(h_o)
        if a_o: a_opens.append(a_o)

    result = {}
    if h_opens:
        result['home_open'] = statistics.median(h_opens)
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
driver = make_driver()

try:
    for g in TARGETS:
        home_slug = g['home'].lower().replace(' ', '-')
        away_slug = g['away'].lower().replace(' ', '-')
        url = f"{BASE}{home_slug}-{away_slug}-{g['match_id']}/"
        print(f"\n[slot{int(g['slot'])}] {g['home']} vs {g['away']}")

        mask = (df['date'] == DATE) & (df['slot'] == g['slot'])
        for bm in g['bms']:
            print(f"  BM: {bm}")
            pop = scrape_3times(driver, url, bm)
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
finally:
    driver.quit()

mask08 = df['date'] == DATE
df.loc[mask08, 'home_change'] = (df.loc[mask08, 'home_close'] - df.loc[mask08, 'home_open']).round(3)
df.loc[mask08, 'away_change'] = (df.loc[mask08, 'away_close'] - df.loc[mask08, 'away_open']).round(3)
df.loc[mask08, 'winner_direction'] = df[mask08].apply(calc_dir, axis=1)

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 저장 완료 ===')
print(f"home_open NaN: {df[mask08]['home_open'].isna().sum()}/70")
print(f"winner_direction NaN: {df[mask08]['winner_direction'].isna().sum()}/70")
print()
print(df[mask08 & df['bookmaker'].isin(['Alphabet','GambleCity','bwin','Kobet']) & df['slot'].isin([1.0,2.0,3.0])][
    ['slot','bookmaker','home_open','home_close','away_open','away_close','winner_direction']
].to_string())
