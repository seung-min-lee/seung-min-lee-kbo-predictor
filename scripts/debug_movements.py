"""
OddsPortal 팝업 전체 구조 확인 - movements 포함 여부
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/doosan-bears-lotte-giants-SQdZWvEj/'
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

driver = make_driver()
driver.get(URL)
try:
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    time.sleep(5)
except:
    time.sleep(5)

try:
    btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
    if btn.is_displayed():
        driver.execute_script('arguments[0].click();', btn)
        time.sleep(1.5)
        print('쿠키 수락')
except:
    pass

# 1xBet 클릭
name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
target_el = None
for nel in name_els:
    if nel.text.strip() == '1xBet':
        target_el = nel
        break

if not target_el:
    print('1xBet 없음')
    driver.quit()
    exit()

row = target_el
for _ in range(3):
    row = row.find_element(By.XPATH, '..')

odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
if not odds_els:
    odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
el = odds_els[0]
driver.execute_script('arguments[0].scrollIntoView(true);', el)
driver.execute_script('window.scrollBy(0,-150);')
time.sleep(0.4)
ActionChains(driver).move_to_element(el).click().perform()
time.sleep(3)
print('클릭 완료')

# 팝업/펼쳐진 영역 전체 구조 덤프
# 방법1: "Opening odds" 포함 div의 부모 탐색
print('\n=== Opening odds 부모 구조 ===')
try:
    open_label = driver.find_element(By.XPATH, "//div[text()='Opening odds:']")
    print('Opening odds: 찾음')
    # 부모 3단계까지
    container = open_label
    for i in range(5):
        container = container.find_element(By.XPATH, '..')
        cls = container.get_attribute('class') or ''
        children = container.find_elements(By.XPATH, './*')
        print('  [+%d] tag=%s cls=%s children=%d' % (i+1, container.tag_name, cls[:60], len(children)))
        if len(children) > 3:
            break

    # 컨테이너 내 모든 div/p 텍스트
    print('\n=== 컨테이너 내 텍스트 요소 ===')
    items = container.find_elements(By.XPATH, './/*[text()]')
    for it in items:
        txt = it.text.strip()
        if txt:
            print('  [%s] %r' % (it.tag_name, txt[:80]))
except Exception as e:
    print('Opening odds 없음:', e)

# 방법2: fixed/absolute 위치 popup div
print('\n=== fixed/popup div ===')
popups = driver.find_elements(By.XPATH,
    "//*[contains(@class,'popup') or contains(@class,'modal') or contains(@class,'tooltip') or contains(@class,'overlay')]")
for p in popups[:5]:
    cls = p.get_attribute('class') or ''
    txt = p.text.strip()[:100]
    if txt:
        print('  [%s] cls=%s | %r' % (p.tag_name, cls[:40], txt))

# 방법3: 새로 나타난 요소 (odds 시간 패턴)
print('\n=== 시간 패턴 (May) 텍스트 ===')
import re
all_els = driver.find_elements(By.XPATH, '//*[contains(text(),"May")]')
for el2 in all_els[:10]:
    txt = el2.text.strip()
    if re.search(r'\d+ May', txt):
        print('  [%s] %r' % (el2.tag_name, txt[:100]))

driver.quit()
print('\n완료')
