import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
df = pd.read_csv('kbo_odds.csv')
print('총 행:', len(df))
print()
for d in ['2026-05-15','2026-05-16','2026-05-17']:
    sub = df[df['date']==d]
    print(f'=== {d} ===')
    for slot in [1.0,2.0,3.0,4.0,5.0]:
        s = sub[sub['slot']==slot]
        if s.empty:
            print(f'  slot{int(slot)}: 없음')
        else:
            h = s.iloc[0]['home']
            a = s.iloc[0]['away']
            w = s.iloc[0]['winner']
            print(f'  slot{int(slot)}: {h} vs {a} (winner={w}) | {len(s)}BM open={s["home_open"].notna().sum()} close={s["home_close"].notna().sum()} wd={s["winner_direction"].notna().sum()}')
