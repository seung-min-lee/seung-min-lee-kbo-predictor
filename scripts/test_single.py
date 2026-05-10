"""단일 경기 테스트 - thread timeout 방식"""
from selenium import webdriver
from selenium.webdriver.common.by import By
import time, os, glob as _glob, threading

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    cached = _glob.glob(os.path.join(os.path.expanduser('~'), '.wdm', 'drivers',
                        'chromedriver', '**', 'chromedriver.exe'), recursive=True)
    from selenium.webdriver.chrome.service import Service
    path = sorted(cached)[-1]
    driver = webdriver.Chrome(service=Service(path), options=options)
    driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def safe_get(driver, url, timeout=90):
    """driver.get()을 별도 스레드에서 실행하고 timeout초 후 반환"""
    t = threading.Thread(target=lambda: driver.get(url), daemon=True)
    t.start()
    t.join(timeout)
    # 페이지가 아직 로딩 중이어도 계속 진행

def main():
    driver = get_driver()
    try:
        print('결과 페이지 로딩 중...')
        safe_get(driver, 'https://www.oddsportal.com/baseball/south-korea/kbo/results/', 60)
        print('safe_get 완료 (60s)')
        time.sleep(3)
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)

        mid = '8OdBucr3'
        url = None
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/h2h/"]')
        print(f'h2h 링크 수: {len(links)}')
        for link in links:
            href = link.get_attribute('href') or ''
            if mid in href:
                url = href
                break

        print(f'URL: {url}')
        if not url:
            print('URL 없음')
            return

        print('h2h 페이지 로딩 중...')
        safe_get(driver, url, 60)
        print('h2h safe_get 완료')
        time.sleep(5)

        nels = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        print(f'BM 수: {len(nels)}')
        for el in nels[:5]:
            print(f'  {el.text.strip()}')

    finally:
        driver.quit()

if __name__ == '__main__':
    main()
