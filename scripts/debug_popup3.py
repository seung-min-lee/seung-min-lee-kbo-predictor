"""
루프 내에서 XPath가 왜 실패하는지 단계별 확인
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

# 쿠키
try:
    btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
    if btn.is_displayed():
        driver.execute_script('arguments[0].click();', btn)
        time.sleep(1.5)
        print('쿠키 수락')
except:
    pass

name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
bm_names = [n.text.strip() for n in name_els if n.text.strip() and n.text.strip() not in FAKE_BMS]
print('BMs:', bm_names)

# 1xBet, 22Bet 두 BM만 테스트
for test_bm in bm_names[:3]:
    print('\n--- %s 테스트 ---' % test_bm)

    # 페이지 새로 로드
    driver.get(URL)
    time.sleep(4)
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1)
    except:
        pass

    name_els2 = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    target_el = None
    for nel in name_els2:
        if nel.text.strip() == test_bm:
            target_el = nel
            break

    if not target_el:
        print('  BM 요소 없음')
        continue

    print('  BM 요소 찾음: %s' % target_el.text)

    try:
        row = target_el
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')
        print('  row tag: %s, class: %s' % (row.tag_name, row.get_attribute('class')[:50]))
    except Exception as e:
        print('  row 탐색 오류:', e)
        continue

    try:
        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        print('  odds_els: %d개 = %s' % (len(odds_els), [e.text for e in odds_els]))
    except Exception as e:
        print('  odds 찾기 오류:', e)
        continue

    if len(odds_els) < 1:
        print('  odds 없음')
        continue

    el = odds_els[0]
    print('  클릭할 element: tag=%s, text=%s' % (el.tag_name, el.text))

    try:
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-150);')
        time.sleep(0.5)
    except Exception as e:
        print('  스크롤 오류:', e)

    # 방법 A: ActionChains
    try:
        ActionChains(driver).move_to_element(el).click().perform()
        time.sleep(3)
        print('  ActionChains 클릭 완료')
    except Exception as e:
        print('  ActionChains 오류:', e)
        continue

    # XPath 찾기
    try:
        open_label = driver.find_element(By.XPATH, "//div[text()='Opening odds:']")
        print('  XPath "Opening odds:" 찾음: %s' % open_label.text)
        try:
            sib = open_label.find_element(By.XPATH, 'following-sibling::*[1]')
            print('  following-sibling text: [%s]' % sib.text)
        except Exception as e:
            print('  following-sibling 오류:', e)
    except Exception as e:
        print('  XPath "Opening odds:" 없음:', e)
        # 현재 URL 확인
        print('  현재 URL:', driver.current_url[:80])
        # 페이지에 BM rows 있는지
        rows_after = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        print('  BM rows after click:', len(rows_after))

    # 닫기 클릭
    try:
        ActionChains(driver).move_to_element(el).click().perform()
        time.sleep(0.5)
    except:
        pass

driver.quit()
print('\n완료')
