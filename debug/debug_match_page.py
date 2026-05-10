"""오늘 경기 상세 페이지 BM 행 구조 확인"""
from playwright.sync_api import sync_playwright
import time, json

URL = 'https://www.oddsportal.com/baseball/h2h/doosan-bears-pGmPNh11/lg-twins-jglLOYoe/#p2TPt1PO'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage','--window-size=1920,1080'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    page = ctx.new_page()
    page.goto(URL, timeout=60000)
    time.sleep(3)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)

    result = page.evaluate("""
    () => {
        // BM 이름 셀렉터 확인
        const nameEls = document.querySelectorAll('p.height-content.pl-4');
        const bms = Array.from(nameEls).map(el => el.innerText.trim()).filter(Boolean);

        // 10x10bet 행의 odds 셀렉터 확인
        let oddsInfo = [];
        for (const nel of nameEls) {
            if (nel.innerText.trim() !== '10x10bet') continue;
            let row = nel;
            for (let i = 0; i < 3; i++) row = row.parentElement;
            // 다양한 셀렉터 시도
            const sel = ['p.odds-text', 'p[class*="height-content"]:not([class*="pl-4"])', 'p[class*="odds"]', '[data-testid="odds"]'];
            sel.forEach(s => {
                const els = Array.from(row.querySelectorAll(s)).map(e => e.innerText.trim());
                oddsInfo.push({selector: s, values: els});
            });
            // 행 HTML 일부
            oddsInfo.push({selector: 'rowHTML', values: [row.innerHTML.substring(0, 800)]});
            break;
        }
        // odds-cell 구조 파악
        const cells = Array.from(document.querySelectorAll('div.odds-cell'));
        const cellInfo = cells.slice(0, 6).map(c => ({
            class: c.className.substring(0, 80),
            html: c.innerHTML.substring(0, 300)
        }));
        // BM별 odds-cell 매핑 시도
        const bmOdds = [];
        for (const nel of Array.from(nameEls).slice(0, 3)) {
            const bmName = nel.innerText.trim();
            let row = nel;
            for (let i = 0; i < 3; i++) row = row.parentElement;
            const oc = Array.from(row.querySelectorAll('div.odds-cell')).map(c => c.innerText.trim());
            bmOdds.push({bm: bmName, cells: oc});
        }
        return { bms: bms.slice(0, 5), oddsInfo, cellInfo, bmOdds };
    }
    """)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
