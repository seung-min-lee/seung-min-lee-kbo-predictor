"""05-06 경기 일부 BM open 재수집 (Momobet, Roobet, Stake.com, VOBET)"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd, time, os, glob as _glob

CSV_PATH = 'kbo_odds.csv'
EXCLUDE  = {'My coupon', 'User Predictions'}
TARGET_BMS = {'Momobet', 'Roobet', 'Stake.com', 'VOBET'}

TARGET_MATCHES = [
    {'match_id': 'p2TPt1PO', 'slot': 1.0, 'wih': True},
    {'match_id': '4Cqae0vI', 'slot': 2.0, 'wih': False},
    {'match_id': 'zXirarug', 'slot': 3.0, 'wih': True},
    {'match_id': 'WboicM95', 'slot': 4.0, 'wih': False},
    {'match_id': 'lGgz14At', 'slot': 5.0, 'wih': True},
]

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    cached = _glob.glob(os.path.join(os.path.expanduser('~'), '.wdm', 'drivers',
                        'chromedriver', '**', 'chromedriver.exe'), recursive=True)
    from selenium.webdriver.chrome.service import Service
    path = sorted(cached)[-1] if cached else None
    if path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
    driver = webdriver.Chrome(service=Service(path), options=options)
    driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def scrape_team_odds(driver, odds_el):
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
        driver.execute_script("window.scrollBy(0,-150);")
        time.sleep(0.5)
        ActionChains(driver).move_to_element(odds_el).click().perform()
        time.sleep(3.0)
    except:
        return None

    data = driver.execute_script("""
        const popup = document.querySelector('div.height-content[class*="bg-gray-med_light"]');
        if (!popup) return {openVal:null,closeVal:null,direction:null,change:null};
        let openVal=null, closeVal=null, direction=null, change=null;
        const openSection = popup.querySelector('div[class*="mt-2"]');
        if (openSection) {
            const boldEls = openSection.querySelectorAll('.font-bold');
            for (const b of boldEls) {
                const v = parseFloat(b.innerText);
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
        if (openVal && closeVal && openVal !== closeVal) {
            direction = closeVal > openVal ? 1 : 0;
            change = (closeVal - openVal).toFixed(2);
        }
        return {openVal, closeVal, direction, change};
    """)

    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        for _ in range(5):
            if not driver.execute_script(
                    "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');"):
                break
            time.sleep(0.3)
    except:
        pass
    return data

def find_url(driver, match_id):
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(4)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)
    links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/h2h/"]')
    for link in links:
        href = link.get_attribute('href') or ''
        if match_id in href:
            return href
    return None

def main():
    df = pd.read_csv(CSV_PATH)
    driver = get_driver()

    try:
        for m in TARGET_MATCHES:
            mid, slot, wih = m['match_id'], m['slot'], m['wih']
            print(f'\n[Slot {int(slot)}] match_id={mid}')

            url = find_url(driver, mid)
            if not url:
                print('  URL 탐색 실패')
                continue
            print(f'  URL: {url}')

            driver.get(url)
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
            except:
                print('  로딩 실패')
                continue
            time.sleep(3)

            name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            target_bms = []
            for nel in name_els:
                name = nel.text.strip()
                if name in TARGET_BMS:
                    target_bms.append((name, nel))

            print(f'  대상 BM 발견: {[b[0] for b in target_bms]}')

            for bm_name, _ in target_bms:
                try:
                    name_els2 = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
                    target_nel = next((el for el in name_els2 if el.text.strip() == bm_name), None)
                    if not target_nel:
                        continue
                    row = target_nel
                    for _ in range(3):
                        row = row.find_element(By.XPATH, '..')
                    odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
                    if len(odds_els) < 2:
                        continue

                    h = scrape_team_odds(driver, odds_els[0])
                    a = scrape_team_odds(driver, odds_els[-1])

                    h_open  = h.get('openVal') if h else None
                    h_close = h.get('closeVal') if h else None
                    a_open  = a.get('openVal') if a else None
                    a_close = a.get('closeVal') if a else None

                    w_dir = None
                    if h_open and h_close and a_open and a_close:
                        hchg = h_close - h_open
                        achg = a_close - a_open
                        wchg = hchg if wih else achg
                        lchg = achg if wih else hchg
                        if wchg > lchg: w_dir = 1
                        elif wchg < lchg: w_dir = 0

                    print(f'    {bm_name}: h_open={h_open} a_open={a_open} w_dir={w_dir}')

                    mask = (df['match_id'] == mid) & (df['bookmaker'] == bm_name)
                    if mask.sum() > 0:
                        if h_open: df.loc[mask, 'home_open'] = h_open
                        if h_close: df.loc[mask, 'home_close'] = h_close
                        if h and h.get('change'): df.loc[mask, 'home_change'] = h.get('change')
                        if h and h.get('direction') is not None: df.loc[mask, 'home_direction'] = h.get('direction')
                        if a_open: df.loc[mask, 'away_open'] = a_open
                        if a_close: df.loc[mask, 'away_close'] = a_close
                        if a and a.get('change'): df.loc[mask, 'away_change'] = a.get('change')
                        if a and a.get('direction') is not None: df.loc[mask, 'away_direction'] = a.get('direction')
                        if w_dir is not None: df.loc[mask, 'winner_direction'] = w_dir
                except Exception as e:
                    print(f'    {bm_name} 실패: {e}')

    finally:
        driver.quit()

    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n저장 완료')

    df2 = pd.read_csv(CSV_PATH)
    chk = df2[(df2['date']=='2026-05-06') & (df2['slot']==1.0)][
        ['bookmaker','home_open','away_open','winner_direction']]
    print('\nSlot1 결과:')
    print(chk.to_string())

if __name__ == '__main__':
    main()
