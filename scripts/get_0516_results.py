"""
05-16 경기 결과 수집 (OddsPortal direct match URL)
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

MATCHES = [
    # (slot, home, away, match_id)
    (1.0, 'KT Wiz Suwon',   'Hanwha Eagles',  'S0DrbHCk',  'kt-wiz-suwon-hanwha-eagles'),
    (2.0, 'Doosan Bears',   'Lotte Giants',   'Aonqhgqt',  'doosan-bears-lotte-giants'),
    (3.0, 'Samsung Lions',  'KIA Tigers',     'z3Y35aKF',  'samsung-lions-kia-tigers'),
    (4.0, 'NC Dinos',       'Kiwoom Heroes',  'rTyC3wkS',  'nc-dinos-kiwoom-heroes'),
    (5.0, 'SSG Landers',    'LG Twins',       'Uk337Lk3',  'ssg-landers-lg-twins'),
]

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'


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


def parse_result(driver, slot, home, away, match_id, slug):
    url = f"{BASE}{slug}-{match_id}/"
    print(f"  URL: {url}")
    driver.get(url)
    time.sleep(6)

    try:
        title = driver.title
        print(f"  타이틀: {title}")
    except:
        pass

    try:
        body = driver.execute_script("return document.body.innerText;")
        lines = [l.strip() for l in body.split('\n') if l.strip()]

        for i, line in enumerate(lines):
            if 'final result' in line.lower() or 'Final' in line:
                print(f"  Final 라인: {line}")
                m = re.search(r'(\d+)\s*[:\-]\s*(\d+)', line)
                if m:
                    s1, s2 = int(m.group(1)), int(m.group(2))
                    print(f"  점수: {s1} vs {s2}")
                    # OddsPortal match page: home team scores s1, away team scores s2
                    if s1 > s2:
                        return home, True
                    elif s2 > s1:
                        return away, False
                    else:
                        return None, None  # 무승부(없음)

            # 점수 패턴이 팀명 근처에
            if re.search(r'^\d+\s*:\s*\d+$', line):
                m = re.search(r'(\d+)\s*:\s*(\d+)', line)
                if m:
                    s1, s2 = int(m.group(1)), int(m.group(2))
                    ctx = ' '.join(lines[max(0,i-2):i+3])
                    print(f"  점수 라인: {line} | 컨텍스트: {ctx[:100]}")
                    if home.split()[0].lower() in ctx.lower() or away.split()[0].lower() in ctx.lower():
                        if s1 > s2:
                            return home, True
                        elif s2 > s1:
                            return away, False

        # 전체 텍스트에서 Final result 패턴
        m = re.search(r'Final result\s+(\d+)\s*[:\-]\s*(\d+)', body, re.IGNORECASE)
        if m:
            s1, s2 = int(m.group(1)), int(m.group(2))
            print(f"  Final result 발견: {s1}:{s2}")
            if s1 > s2:
                return home, True
            elif s2 > s1:
                return away, False

        # 페이지 타이틀에서 점수
        title = driver.title
        m = re.search(r'(\d+)\s*[:\-]\s*(\d+)', title)
        if m:
            s1, s2 = int(m.group(1)), int(m.group(2))
            print(f"  타이틀 점수: {s1}:{s2}")
            if s1 > s2:
                return home, True
            elif s2 > s1:
                return away, False

    except Exception as e:
        print(f"  오류: {e}")

    return None, None


driver = make_driver()
results = {}

try:
    for slot, home, away, match_id, slug in MATCHES:
        print(f"\n[slot{int(slot)}] {home} vs {away}")
        winner, wih = parse_result(driver, slot, home, away, match_id, slug)
        results[slot] = (winner, wih)
        if winner:
            print(f"  ✓ {winner} (wih={wih})")
        else:
            print(f"  ✗ 파싱 실패")
finally:
    driver.quit()

print()
print("=== 최종 결과 ===")
for slot in sorted(results):
    r = results[slot]
    print(f"slot{int(slot)}: {r[0]} wih={r[1]}")
