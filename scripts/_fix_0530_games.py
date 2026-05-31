import sys; sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

# OddsPortal 실제 경기 순서 기준 05-30 정확한 데이터
CORRECT = [
    {'slot':1.0,'home':'Samsung Lions','away':'Doosan Bears',  'home_score':7, 'away_score':8, 'winner':'Doosan Bears','winner_is_home':False},
    {'slot':2.0,'home':'Hanwha Eagles','away':'SSG Landers',   'home_score':13,'away_score':10,'winner':'Hanwha Eagles','winner_is_home':True},
    {'slot':3.0,'home':'LG Twins',     'away':'KIA Tigers',    'home_score':3, 'away_score':1, 'winner':'LG Twins',     'winner_is_home':True},
    {'slot':4.0,'home':'Kiwoom Heroes','away':'KT Wiz Suwon',  'home_score':7, 'away_score':8, 'winner':'KT Wiz Suwon','winner_is_home':False},
    {'slot':5.0,'home':'NC Dinos',     'away':'Lotte Giants',  'home_score':6, 'away_score':2, 'winner':'NC Dinos',    'winner_is_home':True},
]

df = pd.read_csv('kbo_games.csv')
mask_date = df['date'] == '2026-05-30'

# 05-30 행 전체 삭제 후 재삽입
df = df[~mask_date].copy()

new_rows = []
for g in CORRECT:
    new_rows.append({
        'date': '2026-05-30',
        'away': g['away'],
        'home': g['home'],
        'away_score': float(g['away_score']),
        'home_score': float(g['home_score']),
        'winner': g['winner'],
        'winner_is_home': g['winner_is_home'],
        'slot': g['slot'],
    })

df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
df = df.sort_values(['date','slot']).reset_index(drop=True)
df.to_csv('kbo_games.csv', index=False, encoding='utf-8-sig')

print('kbo_games.csv 05-30 수정 완료:')
print(df[df['date']=='2026-05-30'].to_string())
