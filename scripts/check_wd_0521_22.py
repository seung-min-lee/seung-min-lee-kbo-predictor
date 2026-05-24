import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

df = pd.read_csv('kbo_odds.csv')
g = pd.read_csv('kbo_games.csv')

for date in ['2026-05-21', '2026-05-22']:
    print(f'\n======= {date} =======')
    d_g = g[g['date'] == date].sort_values('slot')
    for _, grow in d_g.iterrows():
        slot = grow['slot']
        home = grow['home']; away = grow['away']
        wih = grow['winner_is_home']
        winner = grow['winner']
        print(f'\n  slot{int(slot)} {home} vs {away}  (winner={winner}, wih={wih})')
        if pd.isna(wih):
            print('    결과 없음')
            continue
        w_is_home = bool(wih)
        d_df = df[(df['date'] == date) & (df['slot'] == slot)].head(5)
        for _, r in d_df.iterrows():
            ho = r['home_open']; hc = r['home_close']
            ao = r['away_open']; ac = r['away_close']
            wd_s = r['winner_direction']
            bm = r['bookmaker']
            if any(pd.isna(v) for v in [ho, hc, ao, ac]):
                print(f'    {bm}: open/close 없음 | stored={wd_s}')
                continue
            hchg = round(hc - ho, 4); achg = round(ac - ao, 4)
            wchg = hchg if w_is_home else achg
            lchg = achg if w_is_home else hchg
            if abs(wchg - lchg) < 0.001:
                wd_c = 'N(동일)'
            else:
                wd_c = 1.0 if wchg > lchg else 0.0
            match = 'OK' if str(wd_s) == str(wd_c) else '*** MISMATCH ***'
            print(f'    {bm}: ho={ho} hc={hc} ao={ao} ac={ac} | wchg={wchg} lchg={lchg} | stored={wd_s} calc={wd_c} [{match}]')
