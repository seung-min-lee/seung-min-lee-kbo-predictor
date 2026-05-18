import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

games = pd.read_csv('kbo_games.csv')
games['date'] = pd.to_datetime(games['date'])
games['weekday'] = games['date'].dt.day_name()

# 최근 2주 데이터
recent = games[games['date'] >= '2026-05-01'].sort_values(['date','slot'])

print("=== 최근 날짜별 슬롯 배정 ===")
for date, grp in recent.groupby('date'):
    wd = grp.iloc[0]['weekday']
    print(f"\n{date.date()} ({wd})")
    for _, row in grp.iterrows():
        slot = row['slot']
        home = row['home']
        away = row['away']
        print(f"  slot{int(slot) if not pd.isna(slot) else '?'}: {home} vs {away}")

# kbo_odds.csv 슬롯 배정과 비교
print("\n\n=== kbo_odds.csv 슬롯 배정 (최근) ===")
odds = pd.read_csv('kbo_odds.csv')
recent_odds = odds[odds['date'] >= '2026-05-01']
for date, grp in recent_odds.groupby('date'):
    print(f"\n{date}")
    for slot in sorted(grp['slot'].unique()):
        s = grp[grp['slot']==slot]
        h = s.iloc[0]['home']
        a = s.iloc[0]['away']
        print(f"  slot{int(slot)}: {h} vs {a}")
