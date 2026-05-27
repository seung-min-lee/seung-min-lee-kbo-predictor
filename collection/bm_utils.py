"""
BM 배당 방향 계산 공통 유틸리티
get_slot_bm_odds_seqs 와 완전히 동일한 로직 사용
"""
import pandas as pd
import numpy as np


def compute_winner_direction(home_open, home_close, away_open, away_close, winner_is_home):
    """
    승자 배당 방향 계산 (kbo_update.py get_odds_direction 기준과 동일).

    Returns: 1 (승자 배당 변동 > 패자 배당 변동 = 승자 배당↑ = 이변),
             0 (패자 배당 변동 > 승자 배당 변동 = 승자 배당↓ = 마켓 정배),
             None (N조건 / 데이터 부족)

    N조건:
      - winner_is_home 이 NaN
      - 양쪽 모두 데이터 없음
      - 양쪽 변동량이 동일 (w_chg == l_chg)
    """
    if winner_is_home is None or (isinstance(winner_is_home, float) and pd.isna(winner_is_home)):
        return None

    def _chg(o, c):
        if o is None or c is None:
            return None
        try:
            fo, fc = float(o), float(c)
        except (TypeError, ValueError):
            return None
        if pd.isna(fo) or pd.isna(fc):
            return None
        return round(fc - fo, 4)

    h_chg = _chg(home_open, home_close)
    a_chg = _chg(away_open, away_close)

    if h_chg is None and a_chg is None:
        return None

    w_is_home = bool(winner_is_home)

    if h_chg is not None and a_chg is not None:
        w_chg = h_chg if w_is_home else a_chg
        l_chg = a_chg if w_is_home else h_chg
        if l_chg > w_chg:
            return 0  # 패자 변동 > 승자 변동 → 승자 배당↓ = 마켓 정배
        elif l_chg < w_chg:
            return 1  # 승자 변동 > 패자 변동 → 승자 배당↑ = 이변
        else:
            return None  # N: 변동량 동일

    # 한쪽만 있는 경우: 승자 배당 방향으로 직접 판단
    if h_chg is not None and h_chg != 0:
        h_rose = h_chg > 0
        if w_is_home:
            return 1 if h_rose else 0  # home=승자, 배당↑→1, 배당↓→0
        else:
            return 0 if h_rose else 1  # home=패자, home↑이면 승자(away)는 ↓ → 0

    return None


def recalc_winner_direction(df):
    """
    DataFrame 전체에서 winner_direction 재계산 (기존 값 덮어씌움).
    open/close 데이터가 있고 winner_is_home 이 알려진 행에만 적용.

    항상 기존 값을 덮어써서 stale 오류값을 제거한다.
    """
    df = df.copy()
    has_h   = df['home_open'].notna() & df['home_close'].notna()
    has_wih = df['winner_is_home'].notna()
    update  = (has_h | df['away_open'].notna()) & has_wih

    if not update.any():
        return df

    new_vals = []
    for _, r in df[update].iterrows():
        wd = compute_winner_direction(
            r.get('home_open'),  r.get('home_close'),
            r.get('away_open'),  r.get('away_close'),
            r.get('winner_is_home')
        )
        new_vals.append(wd)

    df.loc[update, 'winner_direction'] = new_vals
    return df
