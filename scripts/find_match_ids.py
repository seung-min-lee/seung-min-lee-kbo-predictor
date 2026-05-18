"""
OddsPortal KBO 결과 페이지에서 05-17 match ID 추출
Whale UA 사용, JS 렌더링 대기
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

WHALE_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Whale/4.29.282.14 Safari/537.36'

TARGET_DATES = ['2026-05-15', '2026-05-17']

# 05-17 예상 경기
GAMES_0517 = [
    (1.0, 'Doosan Bears',  'Lotte Giants'),
    (2.0, 'KT Wiz Suwon', 'Hanwha Eagles'),
    (3.0, 'Samsung Lions', 'KIA Tigers'),
    (4.0, 'NC Dinos',      'Kiwoom Heroes'),
    (5.0, 'SSG Landers',   'LG Twins'),
]

TEAM_KEYWORDS = {
    'Doosan Bears': 'doosan',
    'Lotte Giants': 'lotte',
    'KT Wiz Suwon': 'kt',
    'Hanwha Eagles': 'hanwha',
    'Samsung Lions': 'samsung',
    'KIA Tigers': 'kia',
    'NC Dinos': 'nc',
    'Kiwoom Heroes': 'kiwoom',
    'SSG Landers': 'ssg',
    'LG Twins': 'lg',
}


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


def find_match_links(driver, url, target_date_str):
    """결과 페이지에서 match links 추출"""
    driver.get(url)
    time.sleep(8)
    accept_cookies(driver)
    time.sleep(2)

    # 방법 1: 링크에서 직접 추출
    links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/baseball/south-korea/kbo/"]')
    matches = {}
    for link in links:
        href = link.get_attribute('href') or ''
        m = re.search(r'/kbo/(.+?-([A-Za-z0-9]{8}))/?$', href)
        if m:
            slug = m.group(1)
            mid = m.group(2)
            text = link.text.strip()
            matches[mid] = {'slug': slug, 'text': text, 'href': href}

    print(f'  링크에서 발견된 match IDs: {len(matches)}')
    for mid, info in matches.items():
        print(f'    {mid}: {info["slug"]} | {info["text"][:50]}')

    # 방법 2: window.__injected_redux_state__ 또는 JSON 데이터 추출
    try:
        data = driver.execute_script("""
            // 모든 script 태그에서 JSON 데이터 찾기
            var scripts = document.querySelectorAll('script');
            var found = [];
            for(var s of scripts) {
                var text = s.textContent || '';
                if(text.includes('matchId') || text.includes('match_id')) {
                    found.push(text.substring(0, 500));
                }
            }
            return found;
        """)
        if data:
            print(f'  스크립트에서 matchId 발견: {len(data)}개')
            for d in data[:3]:
                print(f'    {d[:200]}')
    except:
        pass

    # 방법 3: 페이지 전체 HTML에서 match ID 패턴 추출
    try:
        source = driver.page_source
        # KBO match URL 패턴
        pattern = r'/baseball/south-korea/kbo/([a-z0-9-]+-[a-z0-9-]+-([A-Za-z0-9]{8}))/'
        all_matches = re.findall(pattern, source)
        if all_matches:
            print(f'  HTML에서 발견된 패턴: {len(all_matches)}개')
            for slug, mid in set(all_matches):
                print(f'    {mid}: {slug}')
                matches[mid] = {'slug': slug, 'text': '', 'href': f'/baseball/south-korea/kbo/{slug}/'}
    except:
        pass

    return matches


driver = make_driver()
all_matches = {}

try:
    # 결과 페이지 로드
    for page in ['', '#/page/2/']:
        url = f'https://www.oddsportal.com/baseball/south-korea/kbo/results/{page}'
        print(f'\n=== {url} ===')
        ms = find_match_links(driver, url, '17 May 2026')
        all_matches.update(ms)

    # 전체 텍스트에서 05-17 날짜 컨텍스트 찾기
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(8)
    body = driver.execute_script("return document.body.innerHTML;")

    # 05-17 관련 링크 찾기
    print('\n=== HTML에서 05-17 경기 검색 ===')
    # anchor tags with kbo URLs
    pattern = r'href="(/baseball/south-korea/kbo/[^"]+)"[^>]*>([^<]*)'
    for m in re.finditer(pattern, body):
        href = m.group(1)
        text = m.group(2)
        if re.search(r'-[A-Za-z0-9]{8}/?$', href):
            mid = re.search(r'-([A-Za-z0-9]{8})/?$', href)
            if mid:
                print(f'  {mid.group(1)}: {href} | {text[:50]}')

    # 페이지에서 날짜 섹션 찾기
    print('\n=== 날짜별 경기 섹션 ===')
    date_sections = re.finditer(r'(17 May|16 May|15 May)[^<]*(?:<[^>]+>[^<]*)*', body)
    for sec in date_sections:
        print(f'  섹션: {sec.group()[:300]}')

finally:
    driver.quit()

print('\n=== 최종 발견된 Match IDs ===')
for mid, info in sorted(all_matches.items()):
    print(f'  {mid}: {info["slug"]}')
