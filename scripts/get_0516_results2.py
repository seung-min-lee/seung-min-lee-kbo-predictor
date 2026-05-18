"""
05-16 결과 수집 v2 - OddsPortal KBO results 페이지 활용
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

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

driver = make_driver()

try:
    # OddsPortal KBO 2026 results 페이지
    url = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
    print(f"URL: {url}")
    driver.get(url)
    time.sleep(6)

    body = driver.execute_script("return document.body.innerText;")
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    print("=== 05-16 관련 라인 ===")
    found_0516 = False
    for i, line in enumerate(lines):
        if '16 May' in line or '2026-05-16' in line:
            found_0516 = True
            print(f"[{i}] {line}")
        elif found_0516:
            # 날짜 구간 안에서 경기 결과 출력
            if re.search(r'\d{1,2} May', line) and '16 May' not in line:
                found_0516 = False
                break
            print(f"[{i}] {line}")

    print()
    # 전체 텍스트에서 05-16 경기 찾기
    print("=== 팀명 검색 ===")
    teams = ['Doosan', 'Lotte', 'KT Wiz', 'Hanwha', 'Samsung', 'KIA', 'NC Dinos', 'Kiwoom', 'SSG', 'LG Twins']
    for i, line in enumerate(lines):
        for t in teams:
            if t.lower() in line.lower() and re.search(r'\d+\s*[:\-]\s*\d+', line):
                print(f"[{i}] {line}")
                break

finally:
    driver.quit()
