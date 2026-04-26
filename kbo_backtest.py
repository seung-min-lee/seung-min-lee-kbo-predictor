import pandas as pd
import warnings
warnings.filterwarnings('ignore')

CSV_PATH = 'kbo_odds.csv'

df = pd.read_csv(CSV_PATH)
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)

game_df = df.drop_duplicates(subset='match_id')[
    ['match_id', 'date', 'date_order', 'slot', 'home', 'away',
     'winner', 'winner_is_home', 'consensus']
].copy()
game_df['consensus_win'] = (
    ((game_df['consensus'] == 'home') & game_df['winner_is_home']) |
    ((game_df['consensus'] == 'away') & ~game_df['winner_is_home'])
).astype(int)

print('=' * 60)
print('KBO 백테스팅')
print('=' * 60)
print(f'전체 경기: {len(game_df)}경기 | 기간: {df["date"].min()} ~ {df["date"].max()}')
print()


# ─────────────────────────────────────────────────────────
# ① 팀별 최근 승/패 흐름 (최근 10경기)
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('① 팀별 최근 승/패 흐름  (1=승, 0=패, 최근 10경기)')
print('=' * 60)

teams = sorted(set(game_df['home'].tolist() + game_df['away'].tolist()))

for team in teams:
    mask = (game_df['home'] == team) | (game_df['away'] == team)
    recent = game_df[mask].sort_values('date_order').tail(10)

    seq = []
    for _, row in recent.iterrows():
        win = (row['winner'] == team) if pd.notna(row['winner']) else None
        seq.append('1' if win else ('0' if win is False else 'N'))

    seq_str = ''.join(seq)
    wins    = seq.count('1')
    losses  = seq.count('0')
    last    = recent.iloc[-1]
    opp     = last['away'] if last['home'] == team else last['home']
    print(f'  {team:<18} [{seq_str}]  {wins}승 {losses}패  최근: vs {opp} ({last["date"]})')

print()


# ─────────────────────────────────────────────────────────
# ② Slot별 최근 정배/역배 흐름 (최근 10경기)
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('② Slot별 최근 정배/역배 흐름  (1=정배승, 0=역배승, 최근 10경기)')
print('=' * 60)

for slot in sorted(game_df['slot'].dropna().unique()):
    slot_games = game_df[game_df['slot'] == slot].sort_values('date_order').tail(10)

    seq = []
    for _, row in slot_games.iterrows():
        if pd.isna(row['consensus_win']):
            seq.append('N')
        else:
            seq.append(str(int(row['consensus_win'])))

    seq_str  = ''.join(seq)
    fav_wins = seq.count('1')
    und_wins = seq.count('0')
    last     = slot_games.iloc[-1]
    print(f'  Slot {int(slot)}  [{seq_str}]  정배승 {fav_wins} / 역배승 {und_wins}'
          f'  최근: {last["home"]} vs {last["away"]} ({last["date"]})')
