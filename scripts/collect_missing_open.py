"""
05-15, 05-16 전체 BM open/close popup 수집 (ActionChains 클릭 방식)
- 쿠키 수락 후 ActionChains click → 펼쳐진 행에서 Opening/Closing odds 파싱
- 05-15 먼저 실행, BM 수집 성공 시 05-16도 수집
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, statistics, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES = [
    ('2026-05-15', 1.0, 'Doosan Bears',  'Lotte Giants',  'Lotte Giants',  False, 'doosan-bears-lotte-giants-SQdZWvEj'),
    ('2026-05-15', 2.0, 'KT Wiz Suwon',  'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-tUM8ovTq'),
    ('2026-05-15', 3.0, 'Samsung Lions', 'KIA Tigers',    'KIA Tigers',    False, 'samsung-lions-kia-tigers-lWsUhMzA'),
    ('2026-05-15', 4.0, 'NC Dinos',      'Kiwoom Heroes', 'Kiwoom Heroes', False, 'nc-dinos-kiwoom-heroes-AoWxi05M'),
    ('2026-05-15', 5.0, 'SSG Landers',   'LG Twins',      'LG Twins',      False, 'ssg-landers-lg-twins-rZvMfr6c'),
    ('2026-05-16', 1.0, 'KT Wiz Suwon',  'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-S0DrbHCk'),
    ('2026-05-16', 2.0, 'Doosan Bears',  'Lotte Giants',  'Doosan Bears',  True,  'doosan-bears-lotte-giants-Aonqhgqt'),
    ('2026-05-16', 3.0, 'Samsung Lions', 'KIA Tigers',    'Samsung Lions', True,  'samsung-lions-kia-tigers-z3Y35aKF'),
    ('2026-05-16', 4.0, 'NC Dinos',      'Kiwoom Heroes', 'NC Dinos',      True,  'nc-dinos-kiwoom-heroes-rTyC3wkS'),
    ('2026-05-16', 5.0, 'SSG Landers',   'LG Twins',      'SSG Landers',   True,  'ssg-landers-lg-twins-Uk337Lk3'),
]

FAKE_BMS = {'My coupon', 'User Predictions'}


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def accept_cookies(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1)
            print('  쿠키 수락 완료')
    except:
        pass


def load_page(driver, url, first=False):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
    except:
        time.sleep(4)
    if first:
        accept_cookies(driver)
        time.sleep(1)


def _parse_odds_from_sibling(text):
    """'14 May, 22:12\n1.80' 형태에서 마지막 숫자 추출"""
    m = re.findall(r'\d+\.\d+', text)
    return float(m[-1]) if m else None


def get_popup_odds(driver, bm_name, side='home'):
    """BM 배당 클릭 후 XPath로 Opening/Closing odds 파싱 (페이지 리로드 후 호출)"""
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target_el = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target_el = nel
                break
        if not target_el:
            return None, None

        row = target_el
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None, None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-150);')
        time.sleep(0.4)

        ActionChains(driver).move_to_element(el).click().perform()
        time.sleep(2.5)

        open_val = close_val = None
        try:
            open_label = driver.find_element(By.XPATH, "//div[text()='Opening odds:']")
            open_sib = open_label.find_element(By.XPATH, 'following-sibling::*[1]')
            open_val = _parse_odds_from_sibling(open_sib.text)
        except:
            pass
        try:
            close_label = driver.find_element(By.XPATH, "//div[text()='Closing odds:']")
            close_sib = close_label.find_element(By.XPATH, 'following-sibling::*[1]')
            close_val = _parse_odds_from_sibling(close_sib.text)
        except:
            pass

        return open_val, close_val
    except Exception as e:
        return None, None


def scrape_game(driver, url, first_game=False):
    """한 경기 전체 BM open/close 수집 (BM마다 페이지 리로드 후 클릭)"""
    # 첫 로드로 BM 목록 파악
    load_page(driver, url, first=first_game)
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    bm_names = [n.text.strip() for n in name_els if n.text.strip() and n.text.strip() not in FAKE_BMS]
    if not bm_names:
        print('  BM rows 없음')
        return {}
    print('  BMs: %s' % bm_names)

    bm_data = {}
    for bm in bm_names:
        bm_data[bm] = {'ho': [], 'hc': [], 'ao': [], 'ac': []}

        # home 클릭: 리로드 후 클릭
        load_page(driver, url)
        h_o, h_c = get_popup_odds(driver, bm, 'home')
        if h_o: bm_data[bm]['ho'].append(h_o)
        if h_c: bm_data[bm]['hc'].append(h_c)

        # away 클릭: 리로드 후 클릭
        load_page(driver, url)
        a_o, a_c = get_popup_odds(driver, bm, 'away')
        if a_o: bm_data[bm]['ao'].append(a_o)
        if a_c: bm_data[bm]['ac'].append(a_c)

        print('  %s: h_o=%s h_c=%s a_o=%s a_c=%s' % (bm, h_o, h_c, a_o, a_c))

    result = {}
    for bm, vals in bm_data.items():
        r = {}
        if vals['ho']: r['home_open']  = vals['ho'][0]
        if vals['hc']: r['home_close'] = vals['hc'][0]
        if vals['ao']: r['away_open']  = vals['ao'][0]
        if vals['ac']: r['away_close'] = vals['ac'][0]
        if r:
            result[bm] = r
    return result


def calc_dir(ho, hc, ao, ac, wih):
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        hchg = float(hc) - float(ho)
        achg = float(ac) - float(ao)
        wchg = hchg if wih else achg
        lchg = achg if wih else hchg
        if abs(wchg - lchg) < 0.001:
            return np.nan
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
updated = added = skipped_date = 0
popup_available_dates = set()

try:
    for i, (date, slot, home, away, winner, wih, slug) in enumerate(GAMES):
        url = BASE + slug + '/'
        match_id = slug.split('-')[-1]
        print('\n[%s slot%d] %s vs %s' % (date, int(slot), home, away))

        # 05-16은 05-15 성공 후에만
        if date == '2026-05-16' and '2026-05-15' not in popup_available_dates:
            print('  → 05-15 popup 미성공, 05-16 스킵')
            skipped_date += 1
            continue

        bm_results = scrape_game(driver, url, first_game=(i == 0))
        print('  수집 결과: %d BM' % len(bm_results))

        if bm_results:
            popup_available_dates.add(date)

        mask = (df['date'] == date) & (df['slot'] == slot)

        for bm, vals in bm_results.items():
            ho = vals.get('home_open')
            hc = vals.get('home_close')
            ao = vals.get('away_open')
            ac = vals.get('away_close')
            if ho is None and hc is None:
                continue

            bm_mask = mask & (df['bookmaker'] == bm)

            if any(bm_mask):
                if ho: df.loc[bm_mask, 'home_open']  = ho
                if hc: df.loc[bm_mask, 'home_close'] = hc
                if ao: df.loc[bm_mask, 'away_open']  = ao
                if ac: df.loc[bm_mask, 'away_close'] = ac
                if ho and hc: df.loc[bm_mask, 'home_change'] = round(float(hc)-float(ho), 3)
                if ao and ac: df.loc[bm_mask, 'away_change'] = round(float(ac)-float(ao), 3)
                # 기존 close 값까지 포함해 direction 재계산
                row = df[bm_mask].iloc[0]
                eff_hc = hc if hc else row.get('home_close')
                eff_ac = ac if ac else row.get('away_close')
                eff_ho = ho if ho else row.get('home_open')
                eff_ao = ao if ao else row.get('away_open')
                wd = calc_dir(eff_ho, eff_hc, eff_ao, eff_ac, wih)
                if not (isinstance(wd, float) and np.isnan(wd)):
                    df.loc[bm_mask, 'winner_direction'] = wd
                print('  ✓ %s: h%.2f→%.2f a%.2f→%.2f wd=%s' % (
                    bm, ho or 0, hc or 0, ao or 0, ac or 0, wd))
                updated += 1
            else:
                new_row = {
                    'date': date, 'slot': slot, 'home': home, 'away': away,
                    'match_id': match_id, 'bookmaker': bm,
                    'home_open':  float(ho) if ho else float('nan'),
                    'home_close': float(hc) if hc else float('nan'),
                    'away_open':  float(ao) if ao else float('nan'),
                    'away_close': float(ac) if ac else float('nan'),
                    'home_change': round(float(hc)-float(ho), 3) if ho and hc else float('nan'),
                    'away_change': round(float(ac)-float(ao), 3) if ao and ac else float('nan'),
                    'winner': winner, 'winner_is_home': wih,
                    'winner_direction': wd,
                }
                for col in df.columns:
                    if col not in new_row:
                        new_row[col] = float('nan')
                df = pd.concat([df, pd.DataFrame([new_row])[df.columns]], ignore_index=True)
                print('  + %s: 신규 h%.2f→%.2f a%.2f→%.2f wd=%s' % (
                    bm, ho or 0, hc or 0, ao or 0, ac or 0, wd))
                added += 1

        df.to_csv('kbo_odds.csv', index=False)
        print('  → 저장')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 완료: 업데이트 %d / 신규 %d / 날짜스킵 %d ===' % (updated, added, skipped_date))
print()
for date in ['2026-05-15', '2026-05-16']:
    d = df[df['date'] == date]
    if d.empty: continue
    for slot in sorted(d['slot'].unique()):
        s = d[d['slot'] == slot]
        wd_ok = s['winner_direction'].notna().sum()
        open_ok = s['home_open'].notna().sum()
        close_ok = s['home_close'].notna().sum()
        print('%s slot%d: %dBM open=%d close=%d wd=%d' % (
            date, int(slot), len(s), open_ok, close_ok, wd_ok))
