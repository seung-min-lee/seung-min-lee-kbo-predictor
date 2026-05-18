import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
df = pd.read_csv('kbo_odds.csv')
sub = df[df['date']=='2026-05-09']
print(f'05-09 총 {len(sub)}행')
for slot in sorted(sub['slot'].unique()):
    s = sub[sub['slot']==slot]
    h = s.iloc[0]['home']
    a = s.iloc[0]['away']
    w = s.iloc[0]['winner']
    wih = s.iloc[0]['winner_is_home']
    print(f'\nslot{int(slot)}: {h} vs {a} → winner={w} wih={wih}')
    for _, row in s.iterrows():
        ho = row['home_open']
        hc = row['home_close']
        ao = row['away_open']
        ac = row['away_close']
        wd = row['winner_direction']
        print(f'  {row["bookmaker"]:<20} h_o={ho}  h_c={hc}  a_o={ao}  a_c={ac}  wd={wd}')
