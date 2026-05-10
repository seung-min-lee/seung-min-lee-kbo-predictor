import sys; sys.stdout.reconfigure(encoding='utf-8')
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_argument('--headless')
opts.add_argument('--no-sandbox')
opts.add_argument('--window-size=1920,1080')
opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
opts.add_experimental_option('excludeSwitches', ['enable-automation'])
d = webdriver.Chrome(options=opts)
d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

url = 'https://www.oddsportal.com/baseball/south-korea/kbo/doosan-bears-ssg-landers-dO3C2Hoo/'
d.get(url)
WebDriverWait(d, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
time.sleep(4)

CHECK_BMS = ['Alphabet', 'GambleCity', '1xBet', 'Melbet']
name_els = d.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')

for nel in name_els:
    bm = nel.text.strip()
    if bm not in CHECK_BMS:
        continue
    row = nel
    for _ in range(3):
        row = row.find_element(By.XPATH, '..')
    odds_text = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
    odds_link = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
    print(f'\n{bm}: odds-text={len(odds_text)}, odds-link={len(odds_link)}')

    els = odds_text if odds_text else odds_link
    if not els:
        print('  -> odds 요소 없음')
        continue

    el = els[0]
    print(f'  tag={el.tag_name}, class={el.get_attribute("class")[:60]}')

    d.execute_script('arguments[0].scrollIntoView(true);', el)
    d.execute_script('window.scrollBy(0,-100);')
    d.execute_script('arguments[0].click();', el)
    time.sleep(2)

    popup = d.execute_script("""
        return document.querySelector("div[class*='fixed'][class*='height-content']");
    """)
    print(f'  팝업(fixed+height-content): {popup is not None}')
    if popup:
        txt = d.execute_script('return arguments[0].innerText;', popup)
        print(f'  텍스트: {txt[:150]}')
    else:
        candidates = d.execute_script("""
            return Array.from(document.querySelectorAll('div')).filter(d => {
                const c = d.className || '';
                return (c.includes('fixed') || c.includes('popup') || c.includes('tooltip')) && d.innerText.includes('odds');
            }).map(d => ({cls: d.className.substring(0,80), txt: d.innerText.substring(0,80)}));
        """)
        print(f'  후보 팝업: {candidates[:3]}')

    d.execute_script('arguments[0].click();', el)
    time.sleep(0.5)

d.quit()
