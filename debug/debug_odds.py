"""OddsPortal KBO Next Matches 페이지 구조 디버깅"""
from playwright.sync_api import sync_playwright
import time, json

GAMES_URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    print('페이지 로딩...')
    try:
        page.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
        print('domcontentloaded 완료')
    except Exception as e:
        print(f'goto 실패: {e}')
        browser.close()
        exit(1)

    time.sleep(5)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)

    result = page.evaluate("""
    () => {
        const cands = ['div.eventRow', '[class*="eventRow"]', 'a[href*="/h2h/"]', '[data-testid*="event"]'];
        const counts = {};
        cands.forEach(s => { counts[s] = document.querySelectorAll(s).length; });

        // h2h 링크 기반으로 배당 추출 시도
        const rows = document.querySelectorAll('div.eventRow');
        let oddsInfo = [];
        if (rows.length > 0) {
            const row = rows[0];
            const allP = Array.from(row.querySelectorAll('p')).map(p => ({
                class: p.className, text: p.innerText.trim()
            })).filter(p => p.text);
            oddsInfo = allP.slice(0, 20);
        }
        return { counts, oddsInfo, title: document.title };
    }
    """)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
