import pandas as pd
import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('kbo_odds.csv')
games = pd.read_csv('kbo_games.csv')

games_clean = games[games['date'].str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)].copy()
games_clean['slot'] = games_clean['slot'].astype(float)

mismatch_dates = []
for date in sorted(df['date'].unique()):
    g = games_clean[games_clean['date'] == date]
    if len(g) == 0:
        continue
    correct = {(r['home'], r['away']): int(r['slot']) for _, r in g.iterrows() if not pd.isna(r['slot'])}
    o = df[df['date'] == date][['slot', 'home', 'away']].drop_duplicates(['home', 'away'])
    issues = []
    for _, row in o.iterrows():
        key = (row['home'], row['away'])
        if key in correct and int(row['slot']) != correct[key]:
            msg = '  {} vs {}: odds={} -> correct={}'.format(row['home'], row['away'], int(row['slot']), correct[key])
            issues.append(msg)
    if issues:
        mismatch_dates.append((date, issues))

if not mismatch_dates:
    print('슬롯 불일치 없음')
else:
    for date, issues in mismatch_dates:
        print(date + ':')
        for i in issues:
            print(i)
