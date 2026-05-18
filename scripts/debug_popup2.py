"""
단일 BM 클릭 후 DOM 상태 정밀 디버깅
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
TARGET_BM = '1xBet'

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

# 쿠키 수락
try:
    btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
    if btn.is_displayed():
        driver.execute_script('arguments[0].click();', btn)
        time.sleep(1)
        print('쿠키 수락')
except:
    pass

# BM 행 찾기
FAKE_BMS = {'My coupon', 'User Predictions'}
name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
print('BMs:', [n.text.strip() for n in name_els if n.text.strip() not in FAKE_BMS])

for nel in name_els:
    if nel.text.strip() == TARGET_BM:
        row = nel
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')

        print('odds_els:', len(odds_els), [e.text for e in odds_els])
        el = odds_els[0]

        # 스크롤 + 클릭
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-150);')
        time.sleep(0.5)

        print('클릭 전 "Opening odds" 포함 요소 수:',
              driver.execute_script("return document.querySelectorAll('*').length;"))

        ActionChains(driver).move_to_element(el).click().perform()
        time.sleep(3)

        # 방법1: 모든 텍스트에서 Opening odds 찾기 (필터 없음)
        result1 = driver.execute_script("""
            var els = document.querySelectorAll('*');
            for(var i=0; i<els.length; i++) {
                var t = els[i].innerText || '';
                if(t.indexOf('Opening odds:') !== -1) {
                    return {found: true, tag: els[i].tagName, cls: (els[i].className||'').substring(0,100), children: els[i].children.length, text: t.substring(0,300)};
                }
            }
            return {found: false};
        """)
        print('\n=== 방법1: 필터없이 Opening odds: 검색 ===')
        print(result1)

        # 방법2: 소문자 포함
        result2 = driver.execute_script("""
            var els = document.querySelectorAll('*');
            for(var i=0; i<els.length; i++) {
                var t = (els[i].innerText || '').toLowerCase();
                if(t.indexOf('opening odds') !== -1) {
                    return {tag: els[i].tagName, cls: (els[i].className||'').substring(0,100), text: (els[i].innerText||'').substring(0,300)};
                }
            }
            return null;
        """)
        print('\n=== 방법2: 소문자 "opening odds" 검색 ===')
        print(result2)

        # 방법3: textContent 사용
        result3 = driver.execute_script("""
            var els = document.querySelectorAll('*');
            for(var i=0; i<els.length; i++) {
                var t = els[i].textContent || '';
                if(t.indexOf('Opening odds') !== -1 && els[i].children.length < 10) {
                    return {tag: els[i].tagName, cls: (els[i].className||'').substring(0,100), text: t.substring(0,300)};
                }
            }
            return null;
        """)
        print('\n=== 방법3: textContent 검색 ===')
        print(result3)

        # 방법4: XPath
        try:
            xpath_els = driver.find_elements(By.XPATH, "//*[contains(text(),'Opening odds')]")
            print('\n=== 방법4: XPath //*[contains(text(),Opening odds)] ===')
            for xe in xpath_els:
                print('  tag=%s text=%s' % (xe.tag_name, xe.text[:100]))
        except Exception as ex:
            print('XPath 오류:', ex)

        # 현재 화면 상태 (expandedrow 관련)
        expanded = driver.execute_script("""
            var els = document.querySelectorAll('[class*="expand"], [class*="open"], [class*="active"]');
            var res = [];
            for(var e of els) {
                if(e.offsetHeight > 0 && e.offsetWidth > 0) {
                    res.push({cls:(e.className||'').substring(0,80), text:(e.innerText||'').substring(0,80)});
                }
            }
            return res.slice(0,5);
        """)
        print('\n=== expand/open/active 요소 ===')
        for x in expanded:
            print('  class=%s | text=%s' % (x['cls'][:60], x['text'][:60]))

        break

driver.quit()
print('\n완료')
