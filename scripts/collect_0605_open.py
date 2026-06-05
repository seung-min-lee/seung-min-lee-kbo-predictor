"""
2026-06-05 경기 open/close BM 배당 수집
match_ids: WlzntDRp, hfLt2fl4, MZCcbCmT, ncIY3GJi, E99k0YIG
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pandas as pd, time, tempfile

CSV_PATH  = 'kbo_odds.csv'
TARGET_DATE = '2026-06-05'

MATCHES = [
    {'match_id':'WlzntDRp','slot':1.0,'home':'Doosan Bears','away':'Kiwoom Heroes',
     'winner':'Doosan Bears','winner_is_home':True,'home_score':4,'away_score':3,
     'url':'https://www.oddsportal.com/baseball/south-korea/kbo/doosan-bears-kiwoom-heroes-WlzntDRp/#home-away;2'},
    {'match_id':'hfLt2fl4','slot':2.0,'home':'Lotte Giants','away':'Hanwha Eagles',
     'winner':'Hanwha Eagles','winner_is_home':False,'home_score':2,'away_score':9,
     'url':'https://www.oddsportal.com/baseball/south-korea/kbo/lotte-giants-hanwha-eagles-hfLt2fl4/#home-away;2'},
    {'match_id':'MZCcbCmT','slot':3.0,'home':'KIA Tigers','away':'Samsung Lions',
     'winner':'KIA Tigers','winner_is_home':True,'home_score':5,'away_score':2,
     'url':'https://www.oddsportal.com/baseball/south-korea/kbo/kia-tigers-samsung-lions-MZCcbCmT/#home-away;2'},
    {'match_id':'ncIY3GJi','slot':4.0,'home':'SSG Landers','away':'KT Wiz Suwon',
     'winner':'SSG Landers','winner_is_home':True,'home_score':6,'away_score':4,
     'url':'https://www.oddsportal.com/baseball/south-korea/kbo/ssg-landers-kt-wiz-suwon-ncIY3GJi/#home-away;2'},
    {'match_id':'E99k0YIG','slot':5.0,'home':'NC Dinos','away':'LG Twins',
     'winner':'LG Twins','winner_is_home':False,'home_score':4,'away_score':5,
     'url':'https://www.oddsportal.com/baseball/south-korea/kbo/nc-dinos-lg-twins-E99k0YIG/#home-away;2'},
]

CLICK_BMS = ['10x10bet','1xBet','22Bet','Alphabet','BetInAsia','Bets.io','bwin',
             'Cloudbet','GambleCity','Kobet','Melbet']
HOVER_BMS = ['Momobet','Roobet','Stake.com','VOBET']
POPUP_BMS = CLICK_BMS + HOVER_BMS
EXCLUDE   = {'My coupon','User Predictions'}
INIT_BMS  = ['1xBet','22Bet','BetInAsia','Bets.io','Pinnacle','bet365','bwin','Betway']

def _atomic_csv(path, df):
    dir_ = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as f:
            df.to_csv(f, index=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise

PARSE_JS = """
(hover_only) => {
    let popup;
    if (hover_only) {
        const all = Array.from(document.querySelectorAll('div.height-content.absolute'));
        popup = all.find(el => el.className.includes('z-30'));
    } else {
        const all = Array.from(document.querySelectorAll('div.height-content[class*="bg-gray-med_light"]'));
        popup = all.length ? all[0] : null;
    }
    if (!popup) return null;
    const boldArr = Array.from(popup.querySelectorAll('.font-bold'));
    const closeB  = boldArr.find(b => { const v=parseFloat(b.innerText); return !isNaN(v)&&v>1; });
    const closeVal = closeB ? parseFloat(closeB.innerText) : null;
    const mt2 = popup.querySelector('[class*="mt-2"]');
    let openVal = null;
    if (mt2) {
        const mt2Arr = Array.from(mt2.querySelectorAll('.font-bold'));
        const openB  = mt2Arr.find(b => { const v=parseFloat(b.innerText); return !isNaN(v)&&v>1; });
        openVal = openB ? parseFloat(openB.innerText) : null;
    }
    const redEl  = popup.querySelector('[class*="text-red-dark"]');
    const greenEl= popup.querySelector('[class*="text-green-dark"]');
    const change = redEl?redEl.innerText.trim():greenEl?greenEl.innerText.trim():null;
    return {openVal, closeVal, change};
}
"""

def get_bm_list(page):
    names = page.evaluate("""
        () => [...document.querySelectorAll('p.height-content.pl-4')]
              .map(el=>el.innerText.trim()).filter(n=>n)
    """)
    return [n for n in names if n not in EXCLUDE]

def scrape_popup(page, bm, side, hover_only=False):
    el_h = page.evaluate_handle("""
        ([bm,side]) => {
            const nameEls = document.querySelectorAll('p.height-content.pl-4');
            for (const nel of nameEls) {
                if (nel.innerText.trim() !== bm) continue;
                let row=nel;
                for(let i=0;i<3;i++) row=row.parentElement;
                const oddsEls=row.querySelectorAll('p.odds-text');
                if(oddsEls.length<2) return null;
                return side==='home'?oddsEls[0]:oddsEls[oddsEls.length-1];
            }
            return null;
        }
    """, [bm, side])
    el = el_h.as_element()
    if not el:
        return None
    try:
        el.scroll_into_view_if_needed()
        time.sleep(0.3)
        if hover_only:
            el.hover(); time.sleep(1.5)
        else:
            el.hover(); time.sleep(0.2)
            el.click(); time.sleep(2.5)
    except Exception:
        return None
    data = page.evaluate(PARSE_JS, hover_only)
    try:
        page.keyboard.press('Escape') if not hover_only else page.mouse.move(0,0)
        time.sleep(0.4)
    except Exception:
        pass
    return data

def popup_init(page, bm_map):
    for ib in INIT_BMS:
        if ib not in bm_map:
            continue
        if scrape_popup(page, ib, 'home') is not None:
            print(f'  팝업 초기화: {ib}')
            return True
    return False

def compute_winner_dir(h_open, h_close, a_open, a_close, winner_is_home):
    if not (h_open and h_close and a_open and a_close):
        return None
    h_dir = 1 if h_close > h_open else 0
    a_dir = 1 if a_close > a_open else 0
    if h_dir == a_dir:
        return None
    return 1 if (h_dir==1) == winner_is_home else 0

def main():
    df = pd.read_csv(CSV_PATH)
    updated = 0
    new_rows = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--window-size=1920,1080']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width':1920,'height':1080}
        )
        page = ctx.new_page()

        for idx, match in enumerate(MATCHES):
            mid  = match['match_id']
            slot = match['slot']
            home = match['home']
            away = match['away']
            wih  = match['winner_is_home']
            winner = match['winner']
            print(f'\n[{idx+1}/{len(MATCHES)}] slot{int(slot)} {home} vs {away}  ({mid})')

            loaded = False
            for attempt in range(3):
                try:
                    page.goto(match['url'], timeout=45000, wait_until='domcontentloaded')
                    time.sleep(9)
                    page.evaluate("() => { const m=document.querySelector('.overlay-bookie-modal'); if(m) m.remove(); }")
                    time.sleep(0.5)
                    bms_check = page.evaluate(
                        "() => document.querySelectorAll('p.height-content.pl-4').length"
                    )
                    if bms_check == 0:
                        raise Exception(f'BM 셀렉터 0개 (attempt {attempt+1})')
                    loaded = True; break
                except Exception as e:
                    print(f'  로딩 실패 (attempt {attempt+1}): {type(e).__name__}: {e}')
                    time.sleep(3)
            if not loaded:
                print('  → 스킵'); continue

            bm_list = get_bm_list(page)
            print(f'  BM: {bm_list}')
            popup_init(page, {b:True for b in bm_list})

            for bm in POPUP_BMS:
                if bm not in bm_list:
                    continue
                mask = (df['match_id']==mid) & (df['bookmaker']==bm)
                ho = bm in HOVER_BMS
                h = scrape_popup(page, bm, 'home', hover_only=ho)
                a = scrape_popup(page, bm, 'away', hover_only=ho)

                h_open  = h['openVal']  if h else None
                h_close = h['closeVal'] if h else None
                a_open  = a['openVal']  if a else None
                a_close = a['closeVal'] if a else None
                h_chg   = round(h_close-h_open,4) if (h_open and h_close) else None
                a_chg   = round(a_close-a_open,4) if (a_open and a_close) else None
                odds_ratio = round(h_close/a_close,4) if (h_close and a_close) else None
                consensus  = ('home' if odds_ratio and odds_ratio<1 else ('away' if odds_ratio else None))
                h_dir = (1 if h_close>h_open else 0) if (h_open and h_close and h_open!=h_close) else None
                a_dir = (1 if a_close>a_open else 0) if (a_open and a_close and a_open!=a_close) else None
                w_dir = compute_winner_dir(h_open,h_close,a_open,a_close,wih)

                print(f'  {bm}: h_open={h_open} h_close={h_close} | a_open={a_open} a_close={a_close}')

                if mask.any():
                    if h_open: df.loc[mask,['home_open','home_close','home_change']] = [h_open,h_close,h_chg]
                    if a_open: df.loc[mask,['away_open','away_close','away_change']] = [a_open,a_close,a_chg]
                    if h_dir is not None: df.loc[mask,'home_direction'] = h_dir
                    if a_dir is not None: df.loc[mask,'away_direction'] = a_dir
                    if h_open or a_open: df.loc[mask,'winner_direction'] = w_dir
                    if h_open or a_open: updated += 1
                else:
                    new_rows.append({
                        'match_id':mid,'date':TARGET_DATE,'slot':slot,
                        'home':home,'away':away,'winner':winner,'winner_is_home':wih,
                        'home_score':match['home_score'],'away_score':match['away_score'],
                        'bookmaker':bm,
                        'home_open':h_open,'home_close':h_close,'home_change':h_chg,'home_direction':h_dir,
                        'away_open':a_open,'away_close':a_close,'away_change':a_chg,'away_direction':a_dir,
                        'winner_direction':w_dir,'odds_ratio':odds_ratio,'consensus':consensus,
                    })
                    updated += 1
                time.sleep(0.4)

            if updated > 0:
                save_df = df if not new_rows else pd.concat([df,pd.DataFrame(new_rows)],ignore_index=True)
                save_df = save_df.sort_values(['date','slot','bookmaker']).reset_index(drop=True)
                _atomic_csv(CSV_PATH, save_df)
                df = save_df; new_rows.clear()
                print(f'  중간 저장 완료')

            time.sleep(1)

        browser.close()

    print(f'\n완료: 총 {updated}건 업데이트 → {CSV_PATH}')

if __name__ == '__main__':
    main()
