import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
games = pd.read_csv('kbo_games.csv')
sub = games[games['date']>='2026-05-15']
print(sub.to_string())
