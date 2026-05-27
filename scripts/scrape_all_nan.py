import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, statistics, re, pandas as pd, numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'


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


def get_popup_open(driver, bm_name, side='home'):
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target = nel
                break
        if not target:
            return None

        row = target
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-100);')
        time.sleep(0.3)
        driver.execute_script('arguments[0].click();', el)
        time.sleep(2)

        popup = driver.execute_script("""
            return document.querySelector("div[class*='fixed'][class*='height-content']");
        """)
        if not popup:
            return None

        text = driver.execute_script('return arguments[0].innerText;', popup)
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)

        driver.execute_script('arguments[0].click();', el)
        time.sleep(0.4)

        return float(om.group(1)) if om else None
    except:
        return None


def scrape_bm_3times(driver, url, bm_name):
    h_opens, a_opens = [], []
    for attempt in range(3):
        if not load_page(driver, url):
            break
        h_o = get_popup_open(driver, bm_name, 'home')
        a_o = get_popup_open(driver, bm_name, 'away')
        if h_o is not None: h_opens.append(h_o)
        if a_o is not None: a_opens.append(a_o)

    result = {}
    if h_opens:
        result['home_open'] = statistics.median(h_opens)
        if len(h_opens) > 1 and max(h_opens) - min(h_opens) > 0.05:
            print(f'      ⚠ home_open 편차: {h_opens}')
    if a_opens:
        result['away_open'] = statistics.median(a_opens)
        if len(a_opens) > 1 and max(a_opens) - min(a_opens) > 0.05:
            print(f'      ⚠ away_open 편차: {a_opens}')
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


# ── NaN 행 그룹화 ──────────────────────────────────────────
df = pd.read_csv('kbo_odds.csv')
nan_rows = df[df['home_open'].isna()].copy()

# (date, slot, home, away, match_id) 단위로 그룹화
groups = nan_rows.groupby(['date', 'slot', 'home', 'away', 'match_id'])['bookmaker'].apply(list).reset_index()
print(f'총 {len(nan_rows)}건 NaN → {len(groups)}개 경기 그룹')
for _, g in groups.iterrows():
    print(f"  {g['date']} slot{int(g['slot'])} {g['home']} vs {g['away']} ({g['match_id']}): {len(g['bookmaker'])}BM")

print()
driver = make_driver()
success_count = 0
fail_count = 0

try:
    for _, grp in groups.iterrows():
        date = grp['date']
        slot = grp['slot']
        home = grp['home']
        away = grp['away']
        match_id = grp['match_id']
        bms = grp['bookmaker']

        home_slug = home.lower().replace(' ', '-')
        away_slug = away.lower().replace(' ', '-')
        url = f"{BASE}{home_slug}-{away_slug}-{match_id}/"

        print(f"\n[{date} slot{int(slot)}] {home} vs {away} ({len(bms)}BM)")

        mask = (df['date'] == date) & (df['slot'] == slot)

        for bm in bms:
            pop = scrape_bm_3times(driver, url, bm)
            bm_mask = mask & (df['bookmaker'] == bm)
            if pop:
                if 'home_open' in pop:
                    df.loc[bm_mask, 'home_open'] = pop['home_open']
                if 'away_open' in pop:
                    df.loc[bm_mask, 'away_open'] = pop['away_open']
                print(f"  {bm}: h={pop.get('home_open','?')} a={pop.get('away_open','?')}")
                success_count += 1
            else:
                print(f"  {bm}: 실패")
                fail_count += 1

        # 경기 단위로 저장 (중간 손실 방지)
        df.to_csv('kbo_odds.csv', index=False)

finally:
    driver.quit()

# 전체 재계산
all_dates = df['date'].unique()
for date in all_dates:
    mask = df['date'] == date
    df.loc[mask, 'home_change'] = (df.loc[mask, 'home_close'] - df.loc[mask, 'home_open']).round(3)
    df.loc[mask, 'away_change'] = (df.loc[mask, 'away_close'] - df.loc[mask, 'away_open']).round(3)
    df.loc[mask, 'winner_direction'] = df[mask].apply(calc_dir, axis=1)

df.to_csv('kbo_odds.csv', index=False)

print(f'\n=== 완료: 성공 {success_count}건 / 실패 {fail_count}건 ===')
total_nan = df['home_open'].isna().sum()
total_wd_nan = df['winner_direction'].isna().sum()
print(f'남은 home_open NaN: {total_nan}/{len(df)}')
print(f'남은 winner_direction NaN: {total_wd_nan}/{len(df)}')
