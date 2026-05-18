from playwright.sync_api import sync_playwright
import time

URL = 'https://www.oddsportal.com/baseball/h2h/doosan-bears-pGmPNh11/lg-twins-jglLOYoe/#x0SRfiX7'

PARSE_JS = """
    () => {
        const allAbs = Array.from(document.querySelectorAll('div.height-content.absolute'));
        const popup = allAbs.find(el => el.className.includes('z-30'));
        if (!popup) return null;
        const boldArr = Array.from(popup.querySelectorAll('.font-bold'));
        const closeB  = boldArr.find(b => { const v = parseFloat(b.innerText); return !isNaN(v) && v > 1; });
        const closeVal = closeB ? parseFloat(closeB.innerText) : null;
        const mt2 = popup.querySelector('[class*="mt-2"]');
        let openVal = null;
        if (mt2) {
            const mt2Arr = Array.from(mt2.querySelectorAll('.font-bold'));
            const openB  = mt2Arr.find(b => { const v = parseFloat(b.innerText); return !isNaN(v) && v > 1; });
            openVal = openB ? parseFloat(openB.innerText) : null;
        }
        const redEl   = popup.querySelector('[class*="text-red-dark"]');
        const greenEl = popup.querySelector('[class*="text-green-dark"]');
        const change  = redEl ? redEl.innerText.trim() : greenEl ? greenEl.innerText.trim() : null;
        return { openVal, closeVal, change };
    }
"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = ctx.new_page()
    page.goto(URL)
    page.wait_for_selector('p.height-content.pl-4', timeout=30000)
    time.sleep(3)

    try:
        page.locator('text=Home/Away').first.click()
        time.sleep(2)
    except Exception:
        pass

    for bm in ['Momobet', 'Roobet', 'Stake.com', 'VOBET']:
        for side in ['home', 'away']:
            # ElementHandle로 요소 직접 획득
            el_handle = page.evaluate_handle("""
                ([bm, side]) => {
                    const nameEls = document.querySelectorAll('p.height-content.pl-4');
                    for (const nel of nameEls) {
                        if (nel.innerText.trim() !== bm) continue;
                        let row = nel;
                        for (let i = 0; i < 3; i++) row = row.parentElement;
                        const oddsEls = row.querySelectorAll('p.odds-text');
                        if (oddsEls.length < 2) return null;
                        return side === 'home' ? oddsEls[0] : oddsEls[oddsEls.length - 1];
                    }
                    return null;
                }
            """, [bm, side])

            el = el_handle.as_element()
            if not el:
                print(f'{bm} {side}: 요소 없음')
                continue

            # Playwright 내장 hover → scroll + 마우스이동 자동처리
            el.scroll_into_view_if_needed()
            time.sleep(0.3)
            el.hover()
            time.sleep(1.5)

            result = page.evaluate(PARSE_JS)
            print(f'{bm} {side}: {result}')

            # 툴팁 닫기: 빈 곳으로 이동
            page.mouse.move(0, 0)
            time.sleep(0.8)

    input('\n엔터 누르면 종료...')
    browser.close()
