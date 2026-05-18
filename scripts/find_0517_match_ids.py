"""
05-17 경기 OddsPortal match ID 탐색
OddsPortal KBO 결과 페이지에서 05-17 경기 링크 추출
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

WHALE_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Whale/4.29.282.14 Safari/537.36'

TARGET_DATE = '17 May 2026'
TARGET_PAIRS = [
    ('Doosan', 'Lotte'),
    ('KT', 'Hanwha'),
    ('Samsung', 'KIA'),
    ('NC', 'Kiwoom'),
    ('SSG', 'LG'),
]

# KBO results pages
RESULTS_URLS = [
    'https://www.oddsportal.com/baseball/south-korea/kbo/results/',
    'https://www.oddsportal.com/baseball/south-korea/kbo/results/#/page/2/',
]


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
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def accept_cookies(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1)
            print('  쿠키 수락')
    except:
        pass


driver = make_driver()
found = {}

try:
    for i, url in enumerate(RESULTS_URLS):
        print(f'\n로딩: {url}')
        driver.get(url)
        time.sleep(6)
        if i == 0:
            accept_cookies(driver)
            time.sleep(1)

        # 페이지 링크 찾기
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/baseball/south-korea/kbo/"]')
        print(f'  링크 수: {len(links)}')

        for link in links:
            href = link.get_attribute('href') or ''
            text = link.text.strip()

            # match ID 형식 (8자 alphanumeric)
            m = re.search(r'/kbo/(.+?-([A-Za-z0-9]{8}))/?$', href)
            if not m:
                continue

            slug = m.group(1)
            match_id = m.group(2)
            full_text = text.lower()

            # 날짜 확인을 위해 부모 요소 텍스트도 체크
            try:
                parent = link.find_element(By.XPATH, '../..')
                parent_text = parent.text
                if '17 May' not in parent_text and '05/17' not in parent_text and '2026-05-17' not in parent_text:
                    # 주변 텍스트에서 날짜 확인
                    pass
            except:
                parent_text = ''

            print(f'  슬러그: {slug} | ID: {match_id} | 텍스트: {text[:80]}')

    # 전체 페이지 텍스트 덤프
    for i, url in enumerate(RESULTS_URLS):
        driver.get(url)
        time.sleep(6)
        body = driver.execute_script("return document.body.innerText;")
        lines = [l.strip() for l in body.split('\n') if l.strip()]

        print(f'\n=== {url} 텍스트 샘플 ===')
        for j, line in enumerate(lines):
            if '17 May' in line or 'Doosan' in line or 'Samsung' in line:
                print(f'  [{j}] {line[:120]}')
            if j > 200:
                break

finally:
    driver.quit()
