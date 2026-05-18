"""
팝업 CSS 셀렉터 디버깅 v2 - 쿠키 수락 + ActionChains 클릭
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/doosan-bears-lotte-giants-SQdZWvEj/'

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

# 1. 쿠키 동의 버튼 클릭
print('=== 쿠키 동의 처리 ===')
cookie_selectors = [
    '#onetrust-accept-btn-handler',
    'button[id*="accept"]',
    'button[class*="accept"]',
    '.ot-sdk-btn',
    '#accept-recommended-btn-handler',
]
for sel in cookie_selectors:
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, sel)
        for btn in btns:
            if btn.is_displayed():
                print('쿠키 버튼 클릭:', sel, btn.text[:30])
                driver.execute_script('arguments[0].click();', btn)
                time.sleep(1)
                break
    except:
        pass

time.sleep(2)

# 2. BM 찾기
FAKE_BMS = {'My coupon', 'User Predictions'}
name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
bm_names = [n.text.strip() for n in name_els if n.text.strip() and n.text.strip() not in FAKE_BMS]
print('BMs:', bm_names)

first_bm = bm_names[0] if bm_names else None
if first_bm:
    for nel in name_els:
        if nel.text.strip() == first_bm:
            row = nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if not odds_els:
                odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
            print('odds_els:', len(odds_els))
            if not odds_els:
                print('odds_els 없음! 다른 셀렉터 시도')
                # 대안 셀렉터
                for sel in ['[class*="odds"]', 'span[class*="odds"]', 'div[class*="odds"]']:
                    alt = row.find_elements(By.CSS_SELECTOR, sel)
                    if alt:
                        print('  대안 셀렉터 %s: %d개' % (sel, len(alt)))
                break

            el = odds_els[0]
            print('클릭 대상 text:', el.text, '| tag:', el.tag_name)

            # 방법1: JS 클릭
            print('\n--- 방법1: JS click ---')
            driver.execute_script('arguments[0].scrollIntoView(true);', el)
            driver.execute_script('window.scrollBy(0,-150);')
            time.sleep(0.5)
            driver.execute_script('arguments[0].click();', el)
            time.sleep(3)
            popup1 = driver.execute_script(
                "return document.querySelector(\"div[class*='fixed'][class*='height-content']\");")
            print('기존 셀렉터 결과:', popup1)

            # 모든 새로 생긴 요소 확인
            all_text = driver.execute_script("""
                var els = document.querySelectorAll('*');
                var res = [];
                for(var e of els) {
                    var t = (e.innerText || '');
                    if(t.includes('Opening') || t.includes('Closing') || t.includes('opening') || t.includes('closing')) {
                        if(e.children.length < 8) {
                            res.push({tag: e.tagName, cls: (e.className||'').substring(0,150), txt: t.substring(0,200)});
                        }
                    }
                }
                return res.slice(0,10);
            """)
            print('Opening/Closing 텍스트 포함 요소:')
            for x in all_text:
                print('  [%s] class=%s' % (x['tag'], x['cls'][:80]))
                print('       text=%s' % x['txt'][:100])

            # 방법2: JS 클릭 후 닫고 ActionChains로 재시도
            # 먼저 클릭해서 팝업 닫기
            driver.execute_script('arguments[0].click();', el)
            time.sleep(0.5)

            print('\n--- 방법2: ActionChains click ---')
            driver.execute_script('arguments[0].scrollIntoView(true);', el)
            driver.execute_script('window.scrollBy(0,-150);')
            time.sleep(0.5)
            ActionChains(driver).move_to_element(el).click().perform()
            time.sleep(3)

            all_text2 = driver.execute_script("""
                var els = document.querySelectorAll('*');
                var res = [];
                for(var e of els) {
                    var t = (e.innerText || '');
                    if(t.includes('Opening') || t.includes('Closing')) {
                        if(e.children.length < 8) {
                            res.push({tag: e.tagName, cls: (e.className||'').substring(0,150), txt: t.substring(0,200)});
                        }
                    }
                }
                return res.slice(0,10);
            """)
            print('ActionChains 후 Opening/Closing 포함 요소:')
            for x in all_text2:
                print('  [%s] class=%s' % (x['tag'], x['cls'][:80]))
                print('       text=%s' % x['txt'][:100])
            break

driver.quit()
print('\n완료')
