"""05-23 kbo_games.csv winner/score 수정 (home/away 기반 매칭)"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

# results 페이지에서 수집된 실제 결과 (home, away, home_score, away_score, winner_is_home)
RESULTS_0523 = [
    ('Hanwha Eagles', 'Doosan Bears',   5,  2, True),
    ('KIA Tigers',    'SSG Landers',    5,  4, True),
    ('KT Wiz Suwon',  'NC Dinos',      10,  5, True),
    ('Lotte Giants',  'Samsung Lions',  7,  5, True),
    ('LG Twins',      'Kiwoom Heroes',  5,  2, True),
]

RESULTS_0524 = [
    ('Hanwha Eagles', 'Doosan Bears',   5,  2, True),
    ('KIA Tigers',    'SSG Landers',    3,  2, True),
    ('LG Twins',      'Kiwoom Heroes',  6,  4, True),
    ('KT Wiz Suwon',  'NC Dinos',       5,  8, False),
    ('Lotte Giants',  'Samsung Lions',  0, 10, False),
]

g = pd.read_csv('kbo_games.csv')
print('=== 수정 전 05-23/24 ===')
for date in ['2026-05-23', '2026-05-24']:
    d = g[g['date'] == date].sort_values('slot')
    for _, r in d.iterrows():
        print(f'  {date} slot{int(r["slot"])}: {r["home"]} vs {r["away"]}  winner={r["winner"]}  wih={r["winner_is_home"]}')

# 05-23: 기존 slot 유지, home/away로 매칭하여 winner/score 업데이트
for home, away, hs, as_, wih in RESULTS_0523:
    mask = (g['date'] == '2026-05-23') & (g['home'] == home) & (g['away'] == away)
    if mask.any():
        winner = home if wih else away
        g.loc[mask, 'winner']         = winner
        g.loc[mask, 'winner_is_home'] = wih
        g.loc[mask, 'home_score']     = hs
        g.loc[mask, 'away_score']     = as_
        slot = g.loc[mask, 'slot'].iloc[0]
        print(f'  05-23 slot{int(slot)} {home} vs {away} → winner={winner}')
    else:
        print(f'  05-23 {home} vs {away}: 기존 행 없음')

# 05-24: 결과 페이지 순서 그대로 신규 추가 (없으면 추가, 있으면 업데이트)
for i, (home, away, hs, as_, wih) in enumerate(RESULTS_0524, 1):
    mask = (g['date'] == '2026-05-24') & (g['home'] == home) & (g['away'] == away)
    winner = home if wih else away
    if mask.any():
        g.loc[mask, 'winner']         = winner
        g.loc[mask, 'winner_is_home'] = wih
        g.loc[mask, 'home_score']     = hs
        g.loc[mask, 'away_score']     = as_
        print(f'  05-24 slot{int(g.loc[mask,"slot"].iloc[0])} {home} vs {away} → winner={winner} (업데이트)')
    else:
        new_row = {
            'date': '2026-05-24', 'home': home, 'away': away,
            'home_score': hs, 'away_score': as_,
            'winner': winner, 'winner_is_home': wih,
            'slot': float(i),
        }
        g = pd.concat([g, pd.DataFrame([new_row])], ignore_index=True)
        print(f'  05-24 slot{i} {home} vs {away} → winner={winner} (신규)')

g.to_csv('kbo_games.csv', index=False)
print('\n=== 수정 후 05-23/24 ===')
g2 = pd.read_csv('kbo_games.csv')
for date in ['2026-05-23', '2026-05-24']:
    d = g2[g2['date'] == date].sort_values('slot')
    for _, r in d.iterrows():
        print(f'  {date} slot{int(r["slot"])}: {r["home"]} vs {r["away"]}  winner={r["winner"]}  score={r["home_score"]}-{r["away_score"]}  wih={r["winner_is_home"]}')
