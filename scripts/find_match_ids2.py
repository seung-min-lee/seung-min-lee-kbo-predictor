"""
OddsPortal 결과 페이지 JS 렌더링 후 match ID 추출
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

WHALE_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Whale/4.29.282.14 Safari/537.36'


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument(f'user-agent={WHALE_UA}')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    # 로깅 활성화
    caps = opts.to_capabilities()
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


driver = make_driver()

try:
    url = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
    print(f'로딩: {url}')
    driver.get(url)

    # 쿠키 수락
    time.sleep(4)
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1)
            print('쿠키 수락')
    except:
        pass

    # 페이지가 로드될 때까지 대기
    print('JS 렌더링 대기 (15초)...')
    time.sleep(15)

    # 스크롤하여 lazy load 트리거
    driver.execute_script('window.scrollTo(0, 500);')
    time.sleep(3)
    driver.execute_script('window.scrollTo(0, 1000);')
    time.sleep(3)

    # 링크 재확인
    links = driver.find_elements(By.CSS_SELECTOR, 'a')
    kbo_links = []
    for link in links:
        href = link.get_attribute('href') or ''
        if '/baseball/south-korea/kbo/' in href and href != 'https://www.oddsportal.com/baseball/south-korea/kbo/results/':
            kbo_links.append((href, link.text.strip()))

    print(f'KBO 링크 수: {len(kbo_links)}')
    for href, text in kbo_links[:30]:
        print(f'  {href} | {text[:50]}')

    # HTML 소스에서 패턴 검색
    source = driver.page_source
    pattern = r'/baseball/south-korea/kbo/([a-z0-9-]+-([A-Za-z0-9]{8}))/?'
    found = set(re.findall(pattern, source))
    print(f'\nHTML에서 match slug 발견: {len(found)}개')
    for slug, mid in sorted(found):
        print(f'  {mid}: {slug}')

    # page title 확인
    print(f'\n페이지 타이틀: {driver.title}')
    print(f'현재 URL: {driver.current_url}')

    # body text 확인
    body_text = driver.execute_script("return document.body.innerText;")
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    print(f'\n텍스트 라인 수: {len(lines)}')
    # 팀명 포함 라인 찾기
    for i, line in enumerate(lines):
        if any(t in line for t in ['Doosan', 'Lotte', 'KT Wiz', 'Hanwha', 'Samsung', 'KIA', 'NC Dinos', 'Kiwoom', 'SSG', 'LG Twins']):
            print(f'  [{i}] {line[:120]}')

finally:
    driver.quit()
