"""
H2H 페이지에서 05-15, 05-17 경기 fragment ID 추출
Whale UA 사용
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

WHALE_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Whale/4.29.282.14 Safari/537.36'

# H2H 페이지 URL (팀 slug 사용)
H2H_PAIRS = [
    ('Doosan Bears', 'Lotte Giants',   'doosan-bears-pGmPNh11', 'lotte-giants-pGw4ggkO'),
    ('KT Wiz Suwon', 'Hanwha Eagles',  'kt-wiz-suwon-444SNVEe', 'hanwha-eagles-4tfKodg8'),
    ('Samsung Lions', 'KIA Tigers',    'samsung-lions-O6nTMCG7', 'kia-tigers-rXhOpG8E'),
    ('NC Dinos', 'Kiwoom Heroes',      'nc-dinos-O6x8hD4U', 'kiwoom-heroes-xjpHPEWl'),
    ('SSG Landers', 'LG Twins',        'ssg-landers-fRfCQfHr', 'lg-twins-jglLOYoe'),
]

TARGET_DATES = ['15 May', '16 May', '17 May']


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
    except:
        pass


driver = make_driver()
results = {}  # {(home, away): {date: fragment_id}}

try:
    for i, (home, away, slug1, slug2) in enumerate(H2H_PAIRS):
        url = f'https://www.oddsportal.com/baseball/h2h/{slug1}/{slug2}/'
        print(f'\n[{home} vs {away}]')
        print(f'  URL: {url}')

        driver.get(url)
        time.sleep(10)
        if i == 0:
            accept_cookies(driver)
            time.sleep(1)

        # HTML 소스에서 match fragment IDs 찾기
        source = driver.page_source

        # 패턴 1: #XXXXXXXX:home-away;1 형식
        frags = re.findall(r'#([A-Za-z0-9]{8}):home-away', source)
        print(f'  fragment IDs: {frags}')

        # 패턴 2: href="#XXXXXXXX"
        hrefs = re.findall(r'href="#([A-Za-z0-9]{8})"', source)
        print(f'  href IDs: {hrefs}')

        # 날짜 컨텍스트로 매칭
        body_text = driver.execute_script("return document.body.innerText;")
        lines = [l.strip() for l in body_text.split('\n') if l.strip()]

        pair_results = {}
        for target_date in TARGET_DATES:
            for j, line in enumerate(lines):
                if target_date in line:
                    context = ' '.join(lines[max(0,j-2):j+5])
                    print(f'  [{target_date}] 컨텍스트: {context[:200]}')
                    break

        # 링크 요소 직접 확인
        link_els = driver.find_elements(By.CSS_SELECTOR, 'a[href]')
        date_links = []
        for el in link_els:
            href = el.get_attribute('href') or ''
            text = el.text.strip()
            if '#' in href and re.search(r'[A-Za-z0-9]{8}', href.split('#')[-1]):
                frag = href.split('#')[-1].split(':')[0]
                if len(frag) == 8:
                    date_links.append((frag, href, text[:50]))

        print(f'  fragment 링크 수: {len(date_links)}')
        for frag, href, text in date_links[:20]:
            print(f'    {frag}: {text}')

        results[(home, away)] = date_links

finally:
    driver.quit()

print('\n=== 결과 요약 ===')
for pair, links in results.items():
    print(f'{pair[0]} vs {pair[1]}: {len(links)} 링크')
    for frag, href, text in links[:5]:
        print(f'  {frag}: {text}')
