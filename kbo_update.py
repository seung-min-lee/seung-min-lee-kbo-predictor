from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time, os

EXCLUDE = {'My coupon', 'User Predictions'}
CSV_PATH = 'kbo_odds.csv'

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    import os
    if os.environ.get('CI'):
        from selenium.webdriver.chrome.service import Service
        options.binary_location = '/usr/bin/chromium-browser'
        driver = webdriver.Chrome(
            service=Service('/usr/bin/chromedriver'),
            options=options)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options)

    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def get_match_urls(driver):
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
    time.sleep(3)

    match_list = driver.execute_script("""
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
            results.push({
                date:currentDate, url:href,
                match_id:href.split('#')[1],
                home:teams[0]||'', away:teams[1]||'',
                home_score:homeScore||0, away_score:awayScore||0,
                winner_is_home:homeScore>awayScore,
                finished:!isNaN(homeScore)&&!isNaN(awayScore)&&homeScore!==awayScore
            });
        });
        return results;
    """)

    date_counter = {}
    for m in match_list:
        d = m['date']
        date_counter[d] = date_counter.get(d, 0) + 1
        m['slot'] = date_counter[d]
    return match_list

def scrape_match(driver, url, winner_is_home=True):
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  → 로딩 실패')
        return []
    time.sleep(3)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    results = []

    for name_el in name_els:
        name = name_el.text.strip()
        if name in EXCLUDE: continue
        try:
            row = name_el
            for _ in range(3): row = row.find_element(By.XPATH, '..')
        except: continue
        try:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if not odds_els: continue
            odds_el = odds_els[0] if winner_is_home else odds_els[-1]
            driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
            driver.execute_script("window.scrollBy(0,-100);")
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", odds_el)
            time.sleep(2.0)
        except: continue

        data = driver.execute_script("""
            const panels=document.querySelectorAll('.bg-gray-light');
            let openVal=null,closeVal=null,direction=null,change=null;
            for(const panel of panels){
                const h1=panel.querySelector('h1');
                if(h1){
                    const ce=panel.querySelector('.text-green-dark,.text-red-dark');
                    if(ce){change=ce.innerText.trim();
                           direction=ce.classList.contains('text-green-dark')?1:0;}
                    for(const el of panel.querySelectorAll('.font-bold')){
                        const v=parseFloat(el.innerText);
                        if(!isNaN(v)&&v>1){closeVal=v;break;}}
                }else{
                    for(const el of panel.querySelectorAll('.font-bold')){
                        const v=parseFloat(el.innerText);
                        if(!isNaN(v)&&v>1){openVal=v;break;}}
                }
            }
            if(direction===null&&openVal&&closeVal&&openVal!==closeVal){
                direction=closeVal>openVal?1:0;
                change=(closeVal-openVal).toFixed(2);}
            return{openVal,closeVal,direction,change};
        """)

        if data['direction'] is None:
            try: driver.execute_script("arguments[0].click();", odds_el); time.sleep(0.3)
            except: pass
            continue

        results.append({
            'match_id': url.split('#')[-1], 'bookmaker': name,
            'open': data['openVal'], 'close': data['closeVal'],
            'direction': data['direction'], 'change': data['change']
        })

        try:
            driver.execute_script("arguments[0].click();", odds_el)
            for _ in range(5):
                if driver.execute_script(
                    "return document.querySelectorAll('.bg-gray-light').length;") <= 2: break
                time.sleep(0.3)
        except: pass

    return results

# ── 메인 ──────────────────────────────────────────────
driver = get_driver()
new_rows = []

try:
    # 기존 CSV 로드
    if os.path.exists(CSV_PATH):
        existing = pd.read_csv(CSV_PATH)
        existing_ids = set(existing['match_id'].unique())
        print(f'기존 데이터: {len(existing)}행, {len(existing_ids)}개 경기')
    else:
        existing = pd.DataFrame()
        existing_ids = set()
        print('기존 데이터 없음')

    # 경기 목록 수집
    print('경기 목록 수집 중...')
    match_list = get_match_urls(driver)
    print(f'전체 경기: {len(match_list)}개')

    # 새 경기만 필터링
    new_matches = []
    for m in match_list:
        if not m['finished']:
            print(f"  스킵 (미완료): {m['date']} slot{m['slot']} {m['home']} vs {m['away']}")
            continue
        if m['match_id'] in existing_ids:
            print(f"  스킵 (기존): {m['date']} slot{m['slot']} {m['home']} vs {m['away']}")
            continue
        new_matches.append(m)

    print(f'새로 수집할 경기: {len(new_matches)}개')

    # 새 경기 수집
    for match in new_matches:
        print(f"수집: {match['date']} slot{match['slot']} {match['home']} vs {match['away']}")
        rows = []
        for attempt in range(3):
            rows = scrape_match(driver, match['url'], winner_is_home=match['winner_is_home'])
            if rows: break
            print(f'  재시도 {attempt+1}...')
            time.sleep(3)

        for row in rows:
            row.update({
                'date': match['date'], 'slot': match['slot'],
                'home': match['home'], 'away': match['away'],
                'winner': match['home'] if match['winner_is_home'] else match['away'],
                'home_score': match['home_score'], 'away_score': match['away_score']
            })
        new_rows.extend(rows)
        print(f'  → {len(rows)}행 수집')
        time.sleep(2)

except Exception as e:
    print(f'오류 발생: {e}')

finally:
    driver.quit()

# CSV 저장
if new_rows:
    new_df = pd.DataFrame(new_rows)
    if len(existing) > 0:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'완료: {len(new_rows)}행 추가 (총 {len(combined)}행)')
else:
    print('새 데이터 없음')