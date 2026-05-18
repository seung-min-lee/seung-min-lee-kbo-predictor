import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
games = pd.read_csv('kbo_games.csv')
sub = games[games['date']=='2026-05-09']
print('=== kbo_games.csv 05-09 ===')
print(sub.to_string())
print()

odds = pd.read_csv('kbo_odds.csv')
sub2 = odds[odds['date']=='2026-05-09']
print('=== kbo_odds.csv 05-09 요약 ===')
for slot in sorted(sub2['slot'].unique()):
    s = sub2[sub2['slot']==slot]
    h = s.iloc[0]['home']
    a = s.iloc[0]['away']
    w = s.iloc[0]['winner']
    wih = s.iloc[0]['winner_is_home']
    wd_ok = s['winner_direction'].notna().sum()
    print(f'slot{int(slot)}: {h} vs {a} | winner={w} wih={wih} | {len(s)}BM wd={wd_ok}')
