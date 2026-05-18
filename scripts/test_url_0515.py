"""KBO results 페이지에서 05-15 매치 URL 포맷 탐색"""
import sys, os, time, glob as _glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--window-size=1920,1080')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
options.add_experimental_option('excludeSwitches', ['enable-automation'])
cached = _glob.glob(os.path.join(os.path.expanduser('~'), '.wdm', 'drivers',
                    'chromedriver', '**', 'chromedriver.exe'), recursive=True)
from selenium.webdriver.chrome.service import Service
path = sorted(cached)[-1]
driver = webdriver.Chrome(service=Service(path), options=options)
driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

TARGET_IDS = ['SQdZWvEj', 'tUM8ovTq', 'lWsUhMzA', 'AoWxi05M', 'rZvMfr6c']

# KBO results 탐색
print('KBO results 탐색 중...')
driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
time.sleep(5)
driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
time.sleep(2)

# 모든 KBO 관련 링크 수집
kbo_links = []
for l in driver.find_elements(By.CSS_SELECTOR, 'a[href]'):
    href = l.get_attribute('href') or ''
    if 'oddsportal' not in href:
        continue
    if 'kbo' in href or 'h2h' in href or 'baseball' in href:
        kbo_links.append(href)

# match_id가 포함된 링크
matched = {}
for href in kbo_links:
    for tid in TARGET_IDS:
        if tid in href:
            matched[tid] = href

print(f'KBO 링크 총 {len(kbo_links)}개')
print('05-15 매치 링크:')
for tid in TARGET_IDS:
    if tid in matched:
        print(f'  {tid}: {matched[tid]}')
    else:
        print(f'  {tid}: NOT FOUND')

# KBO 링크 포맷 샘플 (처음 10개)
print('\n링크 포맷 샘플:')
for h in kbo_links[:15]:
    print('  ' + h)

# 실제 match URL 테스트 — 발견된 URL로 팝업 테스트
test_id = next((t for t in TARGET_IDS if t in matched), None)
if not test_id:
    print('\nURL 없음 → 직접 구성 시도')
    # KBO 정규 URL 직접 시도
    test_url = 'https://www.oddsportal.com/baseball/south-korea/kbo/doosan-bears-lotte-giants-SQdZWvEj/'
    test_id = 'SQdZWvEj'
else:
    test_url = matched[test_id]

print(f'\n팝업 테스트: {test_url}')
driver.get(test_url)
try:
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    print('BM 로딩 성공')
except Exception:
    print('BM 로딩 실패 — p.height-content.pl-4 없음')
    # 페이지 타이틀/URL 확인
    print('현재 URL:', driver.current_url)
    print('타이틀:', driver.title[:80])
    driver.quit()
    exit()

time.sleep(4)

# BM 목록 + 첫 번째 BM의 홈 배당 클릭
name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
bm_name, odds_el = None, None
for nel in name_els:
    name = nel.text.strip()
    if not name or name in ('My coupon', 'User Predictions'):
        continue
    try:
        row = nel
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')
        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if len(odds_els) >= 2:
            bm_name = name
            odds_el = odds_els[0]
            break
    except:
        continue

print(f'첫 BM: {bm_name}, 클릭...')
driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
driver.execute_script("window.scrollBy(0,-150);")
time.sleep(0.5)
driver.execute_script("arguments[0].click();", odds_el)
time.sleep(3.0)

result = driver.execute_script("""
    const allDivs = [...document.querySelectorAll('div')];
    const fixedDivs = allDivs.filter(d => {
        const s = window.getComputedStyle(d);
        return s.position === 'fixed' && d.innerText && d.innerText.length > 20;
    });
    const openingEl = allDivs.find(d => d.innerText && d.innerText.includes('Opening odds'));
    const bgGrayEl = document.querySelector('div.height-content[class*="bg-gray-med_light"]');
    const fixedHC  = document.querySelector('div[class*="fixed"][class*="height-content"]');
    return {
        fixed_texts: fixedDivs.map(d => d.innerText.substring(0,100)),
        opening_found: !!openingEl,
        opening_text: openingEl ? openingEl.innerText.substring(0,200) : null,
        bg_gray: !!bgGrayEl,
        fixedHC: !!fixedHC,
    };
""")
print('Opening 팝업:', result['opening_found'])
if result['opening_text']:
    print('  텍스트:', result['opening_text'])
print('bg-gray-med_light:', result['bg_gray'])
print('fixed+height-content:', result['fixedHC'])
print('fixed 요소 텍스트:')
for t in result['fixed_texts']:
    print('  ' + t[:80])

driver.quit()
