"""
KBO 공식 홈페이지 경기 결과 스크래퍼
- ASP.NET WebForms: ddlYear/ddlMonth 드롭다운 PostBack으로 월 전환
- seriesId: 정규시즌(0,9,6) / 시범경기(1)
"""
import re
import time
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

CSV_PATH = 'kbo_games.csv'

TEAM_MAP = {
    'KIA': 'KIA Tigers', 'LG': 'LG Twins', '키움': 'Kiwoom Heroes',
    'SSG': 'SSG Landers', '두산': 'Doosan Bears', '삼성': 'Samsung Lions',
    '롯데': 'Lotte Giants', 'NC': 'NC Dinos', 'KT': 'KT Wiz Suwon',
    '한화': 'Hanwha Eagles',
}

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])

    if os.environ.get('CI'):
        from selenium.webdriver.chrome.service import Service as Svc
        options.binary_location = '/usr/bin/chromium-browser'
        return webdriver.Chrome(service=Svc('/usr/bin/chromedriver'), options=options)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options)

def parse_game_text(text):
    """
    '키움11vs2SSG' 형식 파싱 → (away_team, away_score, home_score, home_team)
    원정팀이 앞, 홈팀이 뒤
    """
    m = re.match(r'^([가-힣A-Za-z]+?)(\d+)vs(\d+)([가-힣A-Za-z]+)$', text.strip())
    if not m:
        return None
    away_name, away_s, home_s, home_name = m.groups()
    away_score, home_score = int(away_s), int(home_s)
    away = TEAM_MAP.get(away_name, away_name)
    home = TEAM_MAP.get(home_name, home_name)
    winner_is_home = home_score > away_score
    winner = home if winner_is_home else away
    return {
        'away': away, 'home': home,
        'away_score': away_score, 'home_score': home_score,
        'winner': winner, 'winner_is_home': winner_is_home,
    }

def select_year_month(driver, year, month):
    """ddlYear/ddlMonth 드롭다운으로 월 전환 (PostBack)"""
    # 연도 변경
    sel_year = Select(driver.find_element(By.ID, 'ddlYear'))
    cur_year = sel_year.first_selected_option.get_attribute('value')
    if cur_year != str(year):
        sel_year.select_by_value(str(year))
        time.sleep(2)

    # 월 변경
    sel_month = Select(driver.find_element(By.ID, 'ddlMonth'))
    cur_month = sel_month.first_selected_option.get_attribute('value')
    if cur_month != f'{month:02d}':
        sel_month.select_by_value(f'{month:02d}')
        time.sleep(2)

def scrape_month(driver, year, month):
    """해당 연/월의 정규시즌 경기 전체 수집"""
    try:
        select_year_month(driver, year, month)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span.win, span.lose')))
    except:
        print(f'  {year}-{month:02d}: 경기 없음')
        return []
    time.sleep(1)

    games = driver.execute_script('''
        const games = [];
        let currentDate = '';
        document.querySelectorAll('tr').forEach(tr => {
            const dateTd = tr.querySelector('td.day');
            if (dateTd && dateTd.innerText.trim()) currentDate = dateTd.innerText.trim();

            const gameTd = [...tr.querySelectorAll('td')].find(
                td => /\\dvs\\d/.test(td.innerText));
            if (!gameTd) return;

            games.push({
                raw_date: currentDate,
                game_text: gameTd.innerText.trim().replace(/\\s/g, '')
            });
        });
        return games;
    ''')

    results = []
    for g in games:
        parsed = parse_game_text(g['game_text'])
        if not parsed:
            continue
        # 날짜 파싱: "04.22(수)" → "2026-04-22"
        m = re.match(r'(\d{2})\.(\d{2})', g['raw_date'])
        if not m:
            continue
        mo, day = int(m.group(1)), int(m.group(2))
        date_str = f'{year}-{mo:02d}-{day:02d}'
        results.append({'date': date_str, **parsed})

    return results

def scrape_seasons(years_months, existing_dates=None):
    driver = get_driver()
    all_games = []
    existing_dates = existing_dates or set()

    try:
        # 첫 로드
        driver.get('https://www.koreabaseball.com/Schedule/Schedule.aspx')
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, 'ddlYear')))
        time.sleep(2)

        for year, month in years_months:
            print(f'수집 중: {year}-{month:02d}...')
            games = scrape_month(driver, year, month)
            new = [g for g in games if g['date'] not in existing_dates]
            all_games.extend(new)
            print(f'  → {len(new)}경기 (스킵: {len(games)-len(new)})')
    finally:
        driver.quit()

    return all_games

# ── 메인 ──────────────────────────────────────────────────
if os.path.exists(CSV_PATH):
    existing = pd.read_csv(CSV_PATH)
    existing_dates = set(existing['date'].unique())
    print(f'기존 데이터: {len(existing)}행, {len(existing_dates)}일')
else:
    existing = pd.DataFrame()
    existing_dates = set()
    print('기존 데이터 없음')

# 2024~2026 정규시즌 (4월~10월)
years_months = [
    (y, m) for y in [2024, 2025, 2026] for m in range(4, 11)
]

new_games = scrape_seasons(years_months, existing_dates)

if new_games:
    new_df = pd.DataFrame(new_games)
    cols = ['date', 'away', 'home', 'away_score', 'home_score',
            'winner', 'winner_is_home']
    new_df = new_df[cols]

    combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) > 0 else new_df
    combined = combined.drop_duplicates(subset=['date', 'home', 'away']).sort_values('date')
    combined.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n완료: {len(new_games)}경기 추가 (총 {len(combined)}경기)')
else:
    print('\n새 데이터 없음')
