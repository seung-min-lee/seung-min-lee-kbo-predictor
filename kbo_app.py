import streamlit as st
import json
import pandas as pd
import os
import html
from datetime import datetime

st.set_page_config(
    page_title="KBO 승부 예측",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 팀 정보 ──────────────────────────────────────────────
TEAM_META = {
    "KIA Tigers":     {"abbr": "KIA",  "color": "#EA0029", "bg": "#1a0005"},
    "LG Twins":       {"abbr": "LG",   "color": "#C30452", "bg": "#1a0008"},
    "Kiwoom Heroes":  {"abbr": "KWM",  "color": "#820024", "bg": "#180005"},
    "SSG Landers":    {"abbr": "SSG",  "color": "#CE0E2D", "bg": "#1a0205"},
    "Doosan Bears":   {"abbr": "DSN",  "color": "#131230", "bg": "#060610"},
    "Samsung Lions":  {"abbr": "SAM",  "color": "#074CA1", "bg": "#000d1a"},
    "Lotte Giants":   {"abbr": "LOT",  "color": "#D00F31", "bg": "#1a0005"},
    "NC Dinos":       {"abbr": "NC",   "color": "#315288", "bg": "#05101a"},
    "KT Wiz Suwon":   {"abbr": "KT",   "color": "#231F20", "bg": "#0d0d0d"},
    "Hanwha Eagles":  {"abbr": "HWE",  "color": "#FF6600", "bg": "#1a0a00"},
}

def tm(name):
    return TEAM_META.get(name, {"abbr": name[:3], "color": "#aaaaaa", "bg": "#111111"})

def esc(value):
    return html.escape('' if value is None else str(value))

# ── CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Noto+Sans+KR:wght@400;700;900&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0a12 !important;
}
[data-testid="stAppViewContainer"] > .main {
    background: #0a0a12;
}
[data-testid="stHeader"] { background: transparent !important; }

/* 타이틀 */
.hero-wrap {
    background: linear-gradient(135deg, #0d0d1a 0%, #1a0d2e 40%, #0d1a2e 100%);
    border: 1px solid #2a2a4a;
    border-radius: 16px;
    padding: 32px 40px 24px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.hero-wrap::before {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at 30% 50%, rgba(180,0,60,.15) 0%, transparent 60%),
                radial-gradient(ellipse at 75% 50%, rgba(0,80,200,.12) 0%, transparent 60%);
}
.hero-title {
    font-family: 'Black Han Sans', sans-serif;
    font-size: 2.6rem;
    letter-spacing: 2px;
    background: linear-gradient(90deg, #ff4466, #ffaa00, #44aaff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0; line-height: 1.2;
    position: relative;
}
.hero-sub {
    color: #7788aa;
    font-size: .9rem;
    margin-top: 6px;
    font-family: 'Noto Sans KR', sans-serif;
    position: relative;
}
.hero-badge {
    display: inline-block;
    background: linear-gradient(90deg, #ff3355, #ff6600);
    color: white;
    font-size: .7rem;
    font-weight: 900;
    padding: 3px 10px;
    border-radius: 20px;
    margin-left: 10px;
    vertical-align: middle;
    font-family: 'Noto Sans KR', sans-serif;
}

/* 경기 카드 */
.match-card {
    background: linear-gradient(160deg, #111128 0%, #0d1225 100%);
    border: 1px solid #1e2040;
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.match-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 14px 14px 0 0;
}
.card-home::after { background: var(--hcolor); }
.card-away::after { background: var(--acolor); }
.card-draw::after { background: linear-gradient(90deg, var(--hcolor) 50%, var(--acolor) 50%); }

/* 팀 헤더 */
.teams-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 18px;
}
.team-block {
    text-align: center;
    flex: 1;
}
.team-abbr {
    font-family: 'Black Han Sans', sans-serif;
    font-size: 2rem;
    line-height: 1;
}
.team-name {
    font-size: .72rem;
    color: #8899bb;
    margin-top: 4px;
    font-family: 'Noto Sans KR', sans-serif;
}
.vs-badge {
    flex: 0 0 44px;
    text-align: center;
    font-family: 'Black Han Sans', sans-serif;
    font-size: 1.1rem;
    color: #444466;
}

/* 시퀀스 테이블 */
.seq-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Noto Sans KR', monospace;
    font-size: .82rem;
    margin-bottom: 14px;
}
.seq-table th {
    color: #556688;
    font-weight: 600;
    font-size: .73rem;
    text-align: center;
    padding: 5px 8px;
    border-bottom: 1px solid #1a2040;
    white-space: nowrap;
}
.seq-table td {
    padding: 7px 8px;
    text-align: center;
    border-bottom: 1px solid #131330;
    color: #ccd8ee;
}
.seq-table td:first-child {
    text-align: left;
    color: #7788aa;
    font-size: .75rem;
    white-space: nowrap;
}
.seq-cell {
    font-family: 'Courier New', monospace;
    font-size: 1rem;
    letter-spacing: 3px;
    font-weight: 700;
}
.bit-1 { color: #44ddaa; }
.bit-0 { color: #ff4466; }
.rec-1 { color: #44ddaa; font-weight: 900; }
.rec-0 { color: #ff4466; font-weight: 900; }
.rec-none { color: #556688; }

/* 최종 추천 배너 */
.rec-banner {
    border-radius: 10px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 4px;
}
.rec-home { background: linear-gradient(90deg, rgba(68,221,170,.15), rgba(68,221,170,.05)); border: 1px solid rgba(68,221,170,.3); }
.rec-away { background: linear-gradient(90deg, rgba(255,68,102,.05), rgba(255,68,102,.15)); border: 1px solid rgba(255,68,102,.3); }
.rec-pass { background: rgba(80,80,120,.15); border: 1px solid rgba(80,80,120,.3); }
.rec-label { font-family: 'Black Han Sans', sans-serif; font-size: 1.1rem; }
.rec-label-home { color: #44ddaa; }
.rec-label-away { color: #ff4466; }
.rec-label-pass { color: #7788aa; }
.conf-bar-wrap { flex: 1; margin: 0 16px; }
.conf-bar-bg { background: #1a2040; border-radius: 4px; height: 6px; }
.conf-bar-fill { height: 6px; border-radius: 4px; }
.conf-text { font-size: .78rem; color: #8899bb; margin-top: 3px; text-align: right; }
.ml-info { font-size: .75rem; color: #556688; text-align: right; white-space: nowrap; }
.explain-box {
    background: linear-gradient(160deg, #10172f, #0c1328);
    border: 1px solid #2d426f;
    border-radius: 10px;
    padding: 16px 18px;
    margin: 0 0 18px;
    font-family: 'Noto Sans KR', sans-serif;
    box-shadow: 0 10px 28px rgba(0,0,0,.22);
}
.explain-title {
    color: #e6efff;
    font-size: .92rem;
    font-weight: 900;
    margin-bottom: 10px;
    letter-spacing: .3px;
}
.explain-line {
    color: #c4d2ee;
    font-size: .86rem;
    line-height: 1.75;
    margin-bottom: 4px;
}
.explain-line b { color: #ffffff; font-weight: 900; }
.explain-good { color: #5dffca; font-weight: 900; }
.explain-warn { color: #ffaa00; font-weight: 900; }

/* 섹션 헤더 */
.section-title {
    font-family: 'Black Han Sans', sans-serif;
    font-size: 1.2rem;
    color: #aabbdd;
    letter-spacing: 1px;
    margin: 28px 0 14px;
    padding-left: 12px;
    border-left: 3px solid #4466ff;
}

/* 스탯 카드 */
.stat-card {
    background: linear-gradient(160deg, #111128, #0d1225);
    border: 1px solid #1e2040;
    border-radius: 12px;
    padding: 18px;
    text-align: center;
}
.stat-num {
    font-family: 'Black Han Sans', sans-serif;
    font-size: 2.2rem;
    line-height: 1;
}
.stat-label {
    font-size: .75rem;
    color: #7788aa;
    margin-top: 4px;
    font-family: 'Noto Sans KR', sans-serif;
}

/* 히스토리 행 */
.hist-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 6px;
    background: #0d1020;
    border: 1px solid #181830;
    font-family: 'Noto Sans KR', sans-serif;
    font-size: .8rem;
}
.hist-mark-O { color: #44ddaa; font-weight: 900; font-size: 1.1rem; }
.hist-mark-X { color: #ff4466; font-weight: 900; font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

# ── 데이터 로드 ──────────────────────────────────────────
PRED_PATH   = 'kbo_predictions.json'
LOG_PATH    = 'kbo_verify_log.csv'
USER_PRED_PATH = 'kbo_user_predictions.json'

@st.cache_data(ttl=30)
def load_bm_data():
    """북메이커 집계 데이터 로드"""
    if not os.path.exists('kbo_odds.csv'):
        return pd.DataFrame()
    df = pd.read_csv('kbo_odds.csv')
    date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
    df['date_order'] = df['date'].map(date_map)
    meta = df.drop_duplicates('match_id')[
        ['match_id', 'date', 'date_order', 'home', 'away', 'winner_is_home']
    ].set_index('match_id')
    agg = df.groupby('match_id').agg(
        bm_count=('bookmaker', 'count'),
        home_pct=('consensus', lambda x: (x == 'home').mean()),
    )
    return meta.join(agg).reset_index().sort_values('date_order').reset_index(drop=True)

@st.cache_data(ttl=30)
def load_predictions():
    if not os.path.exists(PRED_PATH):
        return {}
    with open(PRED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

@st.cache_data(ttl=30)
def load_log():
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame()
    df = pd.read_csv(LOG_PATH)
    # 'True'/'False' 문자열 → 1/0, 그 외 pd.to_numeric 처리
    if 'correct' in df.columns:
        df['correct'] = df['correct'].map(
            lambda x: 1 if str(x).strip().lower() in ('1', '1.0', 'true') else
                      (0 if str(x).strip().lower() in ('0', '0.0', 'false') else None)
        ).astype(float)
    return df

def load_user_predictions():
    if not os.path.exists(USER_PRED_PATH):
        return {}
    with open(USER_PRED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_user_predictions(data):
    with open(USER_PRED_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def make_match_key(pred):
    return f"{pred.get('pred_date', '')}|{pred.get('slot', '')}|{pred.get('home', '')}|{pred.get('away', '')}"

def pick_team_from_value(pick):
    if not pick or pick == 'PASS':
        return None
    if '(' in pick and ')' in pick:
        return pick.split('(', 1)[1].split(')', 1)[0]
    return pick

def model_pick_team(pred):
    rec = pred.get('recommendation', 'PASS')
    if rec.startswith('HOME'):
        return pred.get('home')
    if rec.startswith('AWAY'):
        return pred.get('away')
    return None

def find_actual_winner(log_df, pred):
    if len(log_df) == 0:
        return None
    date = str(pred.get('pred_date', ''))[:10]
    home = pred.get('home')
    away = pred.get('away')
    matched = log_df[
        (log_df['date'].astype(str).str[:10] == date) &
        (log_df['home'] == home) &
        (log_df['away'] == away)
    ]
    if len(matched) == 0:
        return None
    actual = matched.iloc[-1].get('actual_winner')
    return None if pd.isna(actual) else actual

def parse_prediction_team(prediction, home, away):
    if not prediction or pd.isna(prediction) or prediction == 'PASS':
        return None
    prediction = str(prediction)
    if prediction.startswith('HOME'):
        if '(' in prediction and ')' in prediction and prediction != 'HOME(1)':
            return prediction.split('(', 1)[1].split(')', 1)[0]
        return home
    if prediction.startswith('AWAY'):
        if '(' in prediction and ')' in prediction and prediction != 'AWAY(0)':
            return prediction.split('(', 1)[1].split(')', 1)[0]
        return away
    return prediction

def parse_actual_team(actual, home, away):
    if actual is None or pd.isna(actual):
        return None
    actual = str(actual)
    if actual == 'HOME(1)':
        return home
    if actual == 'AWAY(0)':
        return away
    return actual

def is_false_value(value):
    if value is False:
        return True
    return str(value).strip().lower() == 'false'

def failure_reason(row):
    home = row.get('home', '')
    away = row.get('away', '')
    pred_team = parse_prediction_team(row.get('prediction', ''), home, away)
    actual_team = parse_actual_team(row.get('actual_winner', ''), home, away)
    conf = float(row.get('confidence', 0) or 0)
    ml_home = float(row.get('ml_home_prob', 0.5) or 0.5)
    ml_away = float(row.get('ml_away_prob', 0.5) or 0.5)

    reasons = []
    if pred_team and actual_team:
        reasons.append(f"패턴은 {pred_team} 쪽을 선택했지만 실제 승자는 {actual_team}였습니다.")

    pred_is_home = pred_team == home
    pred_ml = ml_home if pred_is_home else ml_away
    opp_ml = ml_away if pred_is_home else ml_home
    if pred_team:
        if pred_ml < opp_ml:
            reasons.append(f"ML은 반대편을 더 높게 봤습니다({pred_ml:.0%} vs {opp_ml:.0%}). 패턴 신호가 ML 경고를 덮은 케이스입니다.")
        elif abs(pred_ml - opp_ml) < 0.10:
            reasons.append(f"ML 확률 차이가 작았습니다({ml_home:.0%}/{ml_away:.0%}). 승부가 애초에 박빙 구간이었습니다.")
        else:
            reasons.append(f"ML도 예측 방향을 지지했지만 실제 결과가 반대로 나왔습니다. 패턴과 ML이 동시에 놓친 변동성 경기입니다.")

    if conf >= 0.85:
        reasons.append("고신뢰도 오답입니다. 반복/미러/다수결 패턴이 과거 흐름에 과적합됐을 가능성이 큽니다.")
    elif conf >= 0.75:
        reasons.append("중상위 신뢰도 오답입니다. 보조 신호 충돌 여부를 확인할 필요가 있습니다.")
    else:
        reasons.append("낮은 신뢰도 구간 오답입니다. PASS 기준을 더 엄격히 하면 줄일 수 있는 유형입니다.")

    pattern_reason = row.get('pattern_reason', '')
    if isinstance(pattern_reason, str) and pattern_reason:
        reasons.append(f"당시 패턴 판단: {pattern_reason}")
    else:
        reasons.append("과거 로그에 상세 패턴 판단문이 없어, 현재는 예측/실제/ML/신뢰도 기준으로만 원인을 추정합니다.")

    return reasons

def render_duel_page(predictions, log_df):
    user_preds = load_user_predictions()
    sorted_preds = sorted(predictions.values(), key=lambda x: x.get('slot', 99))

    st.markdown('<div class="section-title">🥊 예측 대결 &nbsp;<span style="color:#445566;font-size:.85rem;font-family:sans-serif">User vs Model</span></div>', unsafe_allow_html=True)
    st.info("각 경기에서 홈승/원정승/PASS를 클릭하면 User 예측이 저장됩니다. 결과가 검증 로그에 들어오면 자동으로 스코어를 계산합니다.")

    if not sorted_preds:
        st.warning("예측 데이터가 없습니다. kbo_predict.py를 먼저 실행하세요.")
        return

    settled_rows = []

    for pred in sorted_preds:
        key = make_match_key(pred)
        home = pred.get('home', '')
        away = pred.get('away', '')
        hm = tm(home)
        am = tm(away)
        rec = pred.get('recommendation', 'PASS')
        conf = pred.get('confidence', 0)
        saved = user_preds.get(key, {})
        user_pick = saved.get('pick')
        user_team = pick_team_from_value(user_pick)
        model_team = model_pick_team(pred)
        actual = find_actual_winner(log_df, pred)

        user_correct = (user_team == actual) if actual and user_team else None
        model_correct = (model_team == actual) if actual and model_team else None
        if actual:
            settled_rows.append((user_correct, model_correct))

        model_label = 'PASS' if model_team is None else f"{model_team} 승"
        actual_label = actual if actual else '결과 대기'
        saved_label = user_pick if user_pick else '아직 선택 안 함'

        st.markdown(f"""
<div class="match-card card-draw" style="--hcolor:{hm['color']};--acolor:{am['color']};margin-bottom:10px">
  <div class="teams-row" style="margin-bottom:12px">
    <div class="team-block">
      <div class="team-abbr" style="color:{hm['color']}">{hm['abbr']} <span style="font-size:.6rem;color:#445566;font-family:'Noto Sans KR',sans-serif;vertical-align:middle">홈</span></div>
      <div class="team-name">{esc(home)}</div>
    </div>
    <div class="vs-badge">VS</div>
    <div class="team-block">
      <div class="team-abbr" style="color:{am['color']}">{am['abbr']} <span style="font-size:.6rem;color:#445566;font-family:'Noto Sans KR',sans-serif;vertical-align:middle">원정</span></div>
      <div class="team-name">{esc(away)}</div>
    </div>
  </div>
  <div class="explain-line"><b>Model</b> {esc(model_label)} · 신뢰도 {conf:.0%} &nbsp;|&nbsp; <b>User</b> {esc(saved_label)} &nbsp;|&nbsp; <b>실제</b> {esc(actual_label)}</div>
</div>
""", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            if st.button(f"{hm['abbr']} 홈승", key=f"duel_home_{key}", use_container_width=True):
                user_preds[key] = {
                    "date": pred.get('pred_date', ''),
                    "slot": pred.get('slot', ''),
                    "home": home,
                    "away": away,
                    "pick": f"HOME({home})",
                    "saved_at": datetime.now().isoformat(timespec='seconds'),
                }
                save_user_predictions(user_preds)
                st.rerun()
        with c2:
            if st.button(f"{am['abbr']} 원정승", key=f"duel_away_{key}", use_container_width=True):
                user_preds[key] = {
                    "date": pred.get('pred_date', ''),
                    "slot": pred.get('slot', ''),
                    "home": home,
                    "away": away,
                    "pick": f"AWAY({away})",
                    "saved_at": datetime.now().isoformat(timespec='seconds'),
                }
                save_user_predictions(user_preds)
                st.rerun()
        with c3:
            if st.button("PASS", key=f"duel_pass_{key}", use_container_width=True):
                user_preds[key] = {
                    "date": pred.get('pred_date', ''),
                    "slot": pred.get('slot', ''),
                    "home": home,
                    "away": away,
                    "pick": "PASS",
                    "saved_at": datetime.now().isoformat(timespec='seconds'),
                }
                save_user_predictions(user_preds)
                st.rerun()
        with c4:
            if actual:
                user_mark = 'O' if user_correct else ('-' if user_team is None else 'X')
                model_mark = 'O' if model_correct else ('-' if model_team is None else 'X')
                st.markdown(f"User **{user_mark}** / Model **{model_mark}**")
            else:
                st.markdown("결과 대기 중")

    # ── 과거 대결 이력 (user_predictions.json × log_df) ─────────────────
    st.markdown('<div class="section-title">📋 대결 이력</div>', unsafe_allow_html=True)

    all_user_preds = load_user_predictions()
    history_rows = []
    for ukey, udata in sorted(all_user_preds.items(), key=lambda x: x[0], reverse=True):
        u_date = udata.get('date', '')
        u_home = udata.get('home', '')
        u_away = udata.get('away', '')
        u_pick = udata.get('pick', '')
        u_slot = udata.get('slot', '')

        # log_df에서 실제 결과 찾기
        matched = pd.DataFrame()
        if len(log_df) > 0:
            matched = log_df[
                (log_df['date'].astype(str).str[:10] == str(u_date)[:10]) &
                (log_df['home'] == u_home) & (log_df['away'] == u_away)
            ]

        if matched.empty:
            actual_str = '결과 대기'
            model_pred_str = '—'
            u_mark = '⏳'; m_mark = '⏳'
        else:
            row = matched.iloc[-1]
            actual_str = str(row.get('actual_winner', ''))
            model_pred_str = str(row.get('prediction', ''))
            # 실제 승팀
            actual_team = parse_actual_team(actual_str, u_home, u_away)
            user_team   = pick_team_from_value(u_pick)
            model_team  = parse_prediction_team(model_pred_str, u_home, u_away)
            u_mark = ('O' if user_team == actual_team else 'X') if user_team and actual_team else '—'
            m_mark = ('O' if model_team == actual_team else 'X') if model_team and actual_team else '—'

        u_color = '#44ddaa' if u_mark == 'O' else '#ff4466' if u_mark == 'X' else '#7788aa'
        m_color = '#44ddaa' if m_mark == 'O' else '#ff4466' if m_mark == 'X' else '#7788aa'
        hm_h = tm(u_home); am_h = tm(u_away)

        history_rows.append((u_mark, m_mark))
        st.markdown(f"""
<div class="hist-row" style="flex-wrap:wrap;gap:6px">
  <span style="color:#556688;min-width:60px;font-size:.75rem">{str(u_date)[:10]}</span>
  <span style="color:#445566;font-size:.72rem">S{u_slot:.0f}</span>
  <span style="color:#aabbdd;flex:1;min-width:120px">
    <span style="color:{hm_h['color']}">{hm_h['abbr']}</span>
    <span style="color:#334"> vs </span>
    <span style="color:{am_h['color']}">{am_h['abbr']}</span>
  </span>
  <span style="color:#7788aa;font-size:.78rem">내 픽 <b style="color:#ccd">{esc(u_pick)}</b></span>
  <span style="color:#556688">→</span>
  <span style="color:#7788aa;font-size:.78rem">실제 <b style="color:#ccd">{esc(actual_str)}</b></span>
  <span style="font-weight:900;color:{u_color}">나:{u_mark}</span>
  <span style="font-weight:900;color:{m_color}">AI:{m_mark}</span>
</div>""", unsafe_allow_html=True)

    # ── 누적 스코어보드 ──────────────────────────────────────
    settled_hist = [(u, m) for u, m in history_rows if u in ('O', 'X') and m in ('O', 'X')]
    today_settled = [(u, m) for u, m in settled_rows if u is not None and m is not None]
    all_settled = settled_hist  # history already includes today via log_df

    u_total = sum(1 for u, _ in all_settled if u == 'O')
    m_total = sum(1 for _, m in all_settled if m == 'O')
    n_settled = len(all_settled)

    st.markdown('<div class="section-title">🏆 누적 스코어</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    u_acc = u_total / n_settled if n_settled else 0
    m_acc = m_total / n_settled if n_settled else 0
    winner_color = '#44ddaa' if u_total > m_total else '#ff4466' if m_total > u_total else '#ffaa00'
    with s1:
        st.markdown(f"<div class='stat-card'><div class='stat-num' style='color:#44ddaa'>{u_total}/{n_settled}</div><div class='stat-label'>나 적중</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div class='stat-card'><div class='stat-num' style='color:#ff4466'>{m_total}/{n_settled}</div><div class='stat-label'>AI 적중</div></div>", unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div class='stat-card'><div class='stat-num' style='color:#44ddaa'>{u_acc:.0%}</div><div class='stat-label'>나 정확도</div></div>", unsafe_allow_html=True)
    with s4:
        st.markdown(f"<div class='stat-card'><div class='stat-num' style='color:#ff4466'>{m_acc:.0%}</div><div class='stat-label'>AI 정확도</div></div>", unsafe_allow_html=True)

predictions = load_predictions()
log_df      = load_log()

# ── 헤더 ─────────────────────────────────────────────────
st.markdown("""
<div class="hero-wrap">
  <div class="hero-title">⚾ KBO 승부 예측 <span class="hero-badge">LIVE 2026</span></div>
  <div class="hero-sub">패턴 분석 + ML 하이브리드 예측 엔진 &nbsp;|&nbsp; 배당변동 · 정배승패 · 팀승패 3중 시퀀스 분석</div>
</div>
""", unsafe_allow_html=True)

if 'app_page' not in st.session_state:
    st.session_state.app_page = 'engine'

nav_left, nav_right = st.columns([5, 1])
with nav_right:
    if st.session_state.app_page == 'engine':
        if st.button("예측 대결 →", use_container_width=True, type="primary"):
            st.session_state.app_page = 'duel'
            st.rerun()
    else:
        if st.button("← 예측 엔진", use_container_width=True, type="primary"):
            st.session_state.app_page = 'engine'
            st.rerun()

if st.session_state.app_page == 'duel':
    render_duel_page(predictions, log_df)
    st.markdown("""
<div style="text-align:center;color:#2a3050;font-size:.75rem;margin-top:40px;font-family:'Noto Sans KR',sans-serif">
  KBO Prediction Duel &nbsp;|&nbsp; User vs Model &nbsp;|&nbsp; 2026
</div>
""", unsafe_allow_html=True)
    st.stop()

# ── 요약 스탯 ────────────────────────────────────────────
if len(log_df) > 0:
    pred_only = log_df[log_df['prediction'] != 'PASS'].copy()
    total     = len(pred_only)
    correct   = int(pred_only['correct'].sum()) if total > 0 else 0
    acc       = correct / total if total > 0 else 0

    last_valid = pred_only[pred_only['correct'].notna()]
    if len(last_valid) > 0:
        streak_val, streak_type = 1, ('O' if last_valid['correct'].iloc[-1] else 'X')
        vals = last_valid['correct'].tolist()
        for i in range(len(vals)-1, 0, -1):
            if vals[i] == vals[i-1]:
                streak_val += 1
            else:
                break
    else:
        streak_val, streak_type = 0, 'O'
    streak_label = f"연속 {'정답' if streak_type=='O' else '오답'}"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-num" style="color:#44ddaa">{correct}/{total}</div>
          <div class="stat-label">전체 적중 / 예측</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        color = "#44ddaa" if acc >= 0.55 else "#ffaa00" if acc >= 0.50 else "#ff4466"
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-num" style="color:{color}">{acc:.1%}</div>
          <div class="stat-label">전체 정확도</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        scolor = "#44ddaa" if streak_type == 'O' else "#ff4466"
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-num" style="color:{scolor}">{streak_val}연속</div>
          <div class="stat-label">{streak_label}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        recent5 = pred_only.tail(5)
        r5_acc  = recent5['correct'].mean() if len(recent5) > 0 else 0
        r5c     = "#44ddaa" if r5_acc >= 0.6 else "#ffaa00" if r5_acc >= 0.4 else "#ff4466"
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-num" style="color:{r5c}">{r5_acc:.1%}</div>
          <div class="stat-label">최근 5경기 정확도</div>
        </div>""", unsafe_allow_html=True)

# ── 경기 카드 ────────────────────────────────────────────
if not predictions:
    st.warning("예측 데이터가 없습니다. kbo_predict.py를 먼저 실행하세요.")
else:
    pred_date_raw = next(iter(predictions.values())).get('pred_date', '')
    st.markdown(f'<div class="section-title">📅 예측 경기 &nbsp;<span style="color:#445566;font-size:.85rem;font-family:sans-serif">{pred_date_raw}</span></div>', unsafe_allow_html=True)

    def render_seq(seq_str):
        out = ''
        s = str(seq_str)
        i = 0
        while i < len(s):
            if s[i] == 'P':
                out += '<span style="color:#cc8800;font-size:.72rem;font-family:Courier New,monospace;font-weight:bold">P</span>'
                i += 1
            elif s[i] == '1':
                out += '<span class="bit-1">1</span>'
                i += 1
            elif s[i] == '0':
                out += '<span class="bit-0">0</span>'
                i += 1
            elif s[i] == 'N':
                out += '<span style="color:#445566;font-family:Courier New,monospace">N</span>'
                i += 1
            else:
                out += s[i]
                i += 1
        return f'<span class="seq-cell">{out}</span>'

    def render_rec(rec):
        if rec is None:   return '<span class="rec-none">?</span>'
        if rec == 1:      return '<span class="rec-1">▲ 1</span>'
        return '<span class="rec-0">▼ 0</span>'

    sorted_preds = sorted(predictions.values(), key=lambda x: x.get('slot', 99))

    for pred in sorted_preds:
        home = pred['home']
        away = pred['away']
        rec  = pred.get('recommendation', 'PASS')
        conf = pred.get('confidence', 0)
        mh   = pred.get('ml_home_prob', 0.5)
        ma   = pred.get('ml_away_prob', 0.5)
        hm   = tm(home)
        am   = tm(away)

        card_cls = 'card-home' if rec.startswith('HOME') else ('card-away' if rec.startswith('AWAY') else 'card-draw')

        # 시퀀스 데이터
        two_col_rows = [
            ("팀&nbsp;승패",  pred.get('home_team_win',''),  pred.get('home_win_rec'),
                              pred.get('away_team_win',''),  pred.get('away_win_rec')),
        ]

        # 슬롯별 북메이커 개별 배당변동 시퀀스 (1=배당↑, 0=배당↓)
        _slot_bm = pred.get('slot_bm', {})
        _bm_dir_seq = ''.join(
            str(v['rec']) if v['rec'] is not None else 'N'
            for _bm, v in sorted(_slot_bm.items())
        ) if _slot_bm else ''

        # 슬롯 정배승/역배승 시퀀스
        _fav_seq       = pred.get('slot_fav_win', '')
        _fav_rec       = pred.get('slot_fav_rec')        # 1=정배승 예상, 0=역배승 예상, None=불규칙
        _fav_team_rec  = pred.get('slot_fav_team_rec')   # 1=홈 추천, 0=원정 추천, None=불확실
        _home_is_fav   = pred.get('home_is_fav')

        if _fav_rec is None:
            _fav_pred_html = '<span style="color:#445566;font-size:.75rem">불규칙</span>'
        else:
            _fav_label = '정배승 예상' if _fav_rec == 1 else '역배승 예상'
            _fav_color = '#44ddaa' if _fav_rec == 1 else '#ff8844'
            _fav_pred_html = f'<span style="color:{_fav_color};font-weight:700;font-size:.75rem">{_fav_label}</span>'

        _hc = hm['color']; _ha = hm['abbr']
        _ac = am['color']; _aa = am['abbr']
        if _fav_team_rec is None:
            _fav_team_html = ''
        elif _fav_team_rec == 1:
            _fav_team_html = f'&nbsp;→&nbsp;<span style="color:{_hc};font-weight:900;font-size:.75rem">홈({_ha}) 유리</span>'
        else:
            _fav_team_html = f'&nbsp;→&nbsp;<span style="color:{_ac};font-weight:900;font-size:.75rem">원정({_aa}) 유리</span>'

        _fav_who = ('홈=정배' if _home_is_fav else '원정=정배') if _home_is_fav is not None else ''
        _fav_who_html = f'<span style="color:#334455;font-size:.68rem">&nbsp;({_fav_who})</span>' if _fav_who else ''

        table_rows = f"""
            <tr>
              <td>배당변동 예측<br><small style='color:#445'>북메이커별</small><br><small style='color:#334;font-size:.65rem'>1=상승&nbsp;0=하락</small></td>
              <td colspan="5">{render_seq(_bm_dir_seq) if _bm_dir_seq else '<span style="color:#445566">-</span>'}</td>
            </tr>
            <tr>
              <td>슬롯&nbsp;정배승/역배승<br><small style='color:#445'>18경기</small><br><small style='color:#334;font-size:.65rem'>1=정배승&nbsp;0=역배승</small></td>
              <td colspan="5">
                {render_seq(_fav_seq) if _fav_seq and _fav_seq != '-' else '<span style="color:#445566">-</span>'}
                &nbsp;&nbsp;{_fav_pred_html}{_fav_team_html}{_fav_who_html}
              </td>
            </tr>"""
        for label, hs, hr, as_, ar in two_col_rows:
            table_rows += f"""
            <tr>
              <td>{label}</td>
              <td>{render_seq(hs)}</td>
              <td>{render_rec(hr)}</td>
              <td style="color:#1e2040">|</td>
              <td>{render_seq(as_)}</td>
              <td>{render_rec(ar)}</td>
            </tr>"""

        # 북메이커 일치도: 1/0 비율(%) 표시
        def agree_pct_html(seq_s):
            s = str(seq_s)
            total = len([c for c in s if c in '10'])
            if total == 0:
                return '<span style="color:#445566">-</span>'
            n1 = s.count('1'); n0 = s.count('0')
            p1 = n1 / total * 100; p0 = n0 / total * 100
            return (f'<span style="color:#44ddaa;font-weight:700">1:{p1:.0f}%</span>'
                    f'<span style="color:#556688"> / </span>'
                    f'<span style="color:#ff4466;font-weight:700">0:{p0:.0f}%</span>'
                    f'<span style="color:#334455;font-size:.7rem"> ({n1}/{total})</span>')

        table_rows += f"""
            <tr>
              <td>북메이커<br><small style='color:#445'>일치도</small></td>
              <td colspan="2" style="text-align:left">{agree_pct_html(pred.get('home_bm_agree',''))}</td>
              <td style="color:#1e2040">|</td>
              <td colspan="2" style="text-align:left">{agree_pct_html(pred.get('away_bm_agree',''))}</td>
            </tr>"""

        if rec.startswith('HOME'):
            banner_cls   = 'rec-home'
            label_cls    = 'rec-label-home'
            label_text   = f'🏠 HOME 승 ({home})'
            bar_color    = '#44ddaa'
        elif rec.startswith('AWAY'):
            banner_cls   = 'rec-away'
            label_cls    = 'rec-label-away'
            label_text   = f'✈ AWAY 승 ({away})'
            bar_color    = '#ff4466'
        else:
            banner_cls   = 'rec-pass'
            label_cls    = 'rec-label-pass'
            label_text   = '— PASS'
            bar_color    = '#4455aa'

        conf_pct = int(conf * 100)
        verified = pred.get('verified', False)
        actual   = pred.get('actual', None)
        correct  = pred.get('correct', None)
        result_badge = ''
        if verified and actual:
            mark = '✅' if correct else '❌'
            result_badge = f'<span style="font-size:.8rem;margin-left:8px;color:#7788aa">{mark} 실제: {actual}</span>'

        # 현재 경기 북메이커 분포 (가장 최근 동일 매치업 기준)
        bm_df = load_bm_data()
        match_bm = bm_df[
            ((bm_df['home'] == home) & (bm_df['away'] == away)) |
            ((bm_df['home'] == away) & (bm_df['away'] == home))
        ].sort_values('date_order').tail(1)

        bm_bar_html = ''
        if len(match_bm) > 0:
            h_pct  = float(match_bm['home_pct'].iloc[0])
            a_pct  = 1 - h_pct
            bm_cnt = int(match_bm['bm_count'].iloc[0])
            h_n    = round(h_pct * bm_cnt)
            a_n    = bm_cnt - h_n
            bm_bar_html = f"""
  <div style="margin:10px 0 14px;padding:10px 14px;background:#0a0d1a;border-radius:8px;border:1px solid #1a2040">
    <div style="display:flex;justify-content:space-between;font-size:.75rem;color:#556688;margin-bottom:6px;font-family:'Noto Sans KR',sans-serif">
      <span style="color:{hm['color']}">{hm['abbr']} 홈 지지 {h_n}개 ({h_pct:.0%})</span>
      <span style="color:#334466">북메이커 {bm_cnt}개</span>
      <span style="color:{am['color']}">{a_n}개 ({a_pct:.0%}) {am['abbr']} 원정 지지</span>
    </div>
    <div style="display:flex;height:10px;border-radius:5px;overflow:hidden">
      <div style="width:{h_pct*100:.1f}%;background:{hm['color']};opacity:.8"></div>
      <div style="width:{a_pct*100:.1f}%;background:{am['color']};opacity:.8"></div>
    </div>
    <div style="font-size:.7rem;color:#334466;margin-top:5px;font-family:'Noto Sans KR',sans-serif">
      {"⚡ 강한 쏠림" if abs(h_pct-0.5)>=0.3 else "〜 균형 배당"} &nbsp;|&nbsp; 최근 매치업 기준
    </div>
  </div>"""

        pattern_reason = pred.get('pattern_reason', '')
        home_win_desc = pred.get('home_win_desc', '')
        away_win_desc = pred.get('away_win_desc', '')
        slot_fav_desc = pred.get('slot_fav_desc', '')
        bm_label = pred.get('bm_label', '')
        if not pattern_reason:
            _home_flow = '승' if pred.get('home_win_rec') == 1 else ('패' if pred.get('home_win_rec') == 0 else '불규칙')
            _away_flow = '승' if pred.get('away_win_rec') == 1 else ('패' if pred.get('away_win_rec') == 0 else '불규칙')
            if rec.startswith('HOME'):
                pattern_reason = f'홈 추천: 홈팀 {_home_flow} 흐름 / 원정팀 {_away_flow} 흐름'
            elif rec.startswith('AWAY'):
                pattern_reason = f'원정 추천: 홈팀 {_home_flow} 흐름 / 원정팀 {_away_flow} 흐름'
            else:
                pattern_reason = 'PASS: 패턴 근거 부족 또는 신호 충돌'

        explain_html = ''
        if pattern_reason:
            home_flow = '승 흐름' if pred.get('home_win_rec') == 1 else ('패 흐름' if pred.get('home_win_rec') == 0 else '불규칙')
            away_flow = '승 흐름' if pred.get('away_win_rec') == 1 else ('패 흐름' if pred.get('away_win_rec') == 0 else '불규칙')
            fav_line = ''
            if slot_fav_desc:
                fav_line = f'<div class="explain-line"><b>슬롯 정배/역배</b> {esc(slot_fav_desc)}</div>'
            bm_line = ''
            if bm_label:
                bm_line = f'<div class="explain-line"><b>BM 배당변동</b> {esc(bm_label)}</div>'

            explain_html = f"""
  <div class="explain-box">
    <div class="explain-title">패턴 예측 설명</div>
    <div class="explain-line"><b>최종 판단</b> <span class="explain-good">{esc(pattern_reason)}</span></div>
    <div class="explain-line"><b>팀 승패</b> {esc(home)}: {home_flow} / {esc(away)}: {away_flow}</div>
    <div class="explain-line"><b>홈 근거</b> {esc(home_win_desc)}</div>
    <div class="explain-line"><b>원정 근거</b> {esc(away_win_desc)}</div>
    {fav_line}
    {bm_line}
    <div class="explain-line"><b>ML 보조</b> 홈 {mh:.0%} / 원정 {ma:.0%}</div>
  </div>"""

        st.markdown(f"""
<div class="match-card {card_cls}" style="--hcolor:{hm['color']};--acolor:{am['color']}">
  <div class="teams-row">
    <div class="team-block">
      <div class="team-abbr" style="color:{hm['color']}">{hm['abbr']} <span style="font-size:.6rem;color:#445566;font-family:'Noto Sans KR',sans-serif;vertical-align:middle">홈</span></div>
      <div class="team-name">{home}</div>
    </div>
    <div class="vs-badge">VS</div>
    <div class="team-block">
      <div class="team-abbr" style="color:{am['color']}">{am['abbr']} <span style="font-size:.6rem;color:#445566;font-family:'Noto Sans KR',sans-serif;vertical-align:middle">원정</span></div>
      <div class="team-name">{away}</div>
    </div>
  </div>
  {bm_bar_html}
  <table class="seq-table">
    <thead>
      <tr>
        <th style="text-align:left">시퀀스</th>
        <th colspan="2" style="color:{hm['color']}">{hm['abbr']} (홈)</th>
        <th></th>
        <th colspan="2" style="color:{am['color']}">{am['abbr']} (원정)</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>

  <div class="rec-banner {banner_cls}">
    <div class="rec-label {label_cls}">{label_text}{result_badge}</div>
    <div class="conf-bar-wrap">
      <div class="conf-bar-bg">
        <div class="conf-bar-fill" style="width:{conf_pct}%;background:{bar_color}"></div>
      </div>
      <div class="conf-text">신뢰도 {conf_pct}%</div>
    </div>
    <div class="ml-info">ML 홈 {mh:.0%} / 원정 {ma:.0%}</div>
  </div>
</div>
""", unsafe_allow_html=True)

        if explain_html:
            st.markdown(explain_html, unsafe_allow_html=True)

        # ── 슬롯별 북메이커 배당변동 패턴 ──────────────────────────
        slot_bm = pred.get('slot_bm', {})

        if slot_bm:
            def bm_seq_html(seq_s):
                s = str(seq_s)
                out = ''
                for ch in s:
                    if ch == '1':
                        out += f'<span style="color:#44ddaa;font-weight:700">{ch}</span>'
                    elif ch == '0':
                        out += f'<span style="color:#ff4466;font-weight:700">{ch}</span>'
                    elif ch == 'N':
                        out += f'<span style="color:#445566">{ch}</span>'
                    else:
                        out += ch
                return f'<span style="font-family:Courier New,monospace;letter-spacing:2px">{out}</span>'

            def rec_badge_bm(rec):
                if rec is None:
                    return ''
                if rec == 1:
                    return '<span style="color:#44ddaa;font-weight:900;font-size:.7rem">▲1 배당↑팀 이김 예측</span>'
                return '<span style="color:#ff4466;font-weight:900;font-size:.7rem">▼0 배당↓팀 이김 예측</span>'

            votes = [v['rec'] for v in slot_bm.values() if v['rec'] is not None]
            v1 = sum(votes)
            v0 = len(votes) - v1

            # 집계 텍스트: 우세한 방향 기준
            if v1 > v0:
                trend_txt = f'<span style="color:#44ddaa">배당↑(1) 우세 {v1}개</span> / <span style="color:#556688">배당↓(0) {v0}개</span>'
            elif v0 > v1:
                trend_txt = f'<span style="color:#556688">배당↑(1) {v1}개</span> / <span style="color:#ff4466">배당↓(0) 우세 {v0}개</span>'
            else:
                trend_txt = f'<span style="color:#7788aa">배당↑(1) {v1}개 / 배당↓(0) {v0}개 동률</span>'

            bm_rows_html = ''
            for bm_name, bm_data in sorted(slot_bm.items()):
                seq_s    = bm_data.get('seq', '-')
                rec_v    = bm_data.get('rec', None)
                desc     = bm_data.get('desc', '')
                cur_odds = bm_data.get('current_odds')
                odds_str = f'{cur_odds:.2f}' if cur_odds else '-'
                badge    = rec_badge_bm(rec_v)
                # 예측 배지를 시퀀스 위에 표시
                seq_cell = f'<div style="line-height:1.6">{badge}<br>{bm_seq_html(seq_s)}</div>' if badge else bm_seq_html(seq_s)
                bm_rows_html += f"""
<tr>
  <td style="color:#7788aa;font-size:.78rem;white-space:nowrap;padding:5px 8px">{bm_name}</td>
  <td style="padding:5px 8px">{seq_cell}</td>
  <td style="color:#556688;font-size:.72rem;padding:5px 8px">{desc}</td>
  <td style="color:#7788aa;font-size:.72rem;padding:5px 8px;text-align:right">{odds_str}</td>
</tr>"""

            st.markdown(f"""
<div style="background:#080c18;border:1px solid #141830;border-radius:10px;padding:16px;margin-bottom:20px">
  <div style="font-size:.8rem;color:#556688;margin-bottom:6px;font-family:'Noto Sans KR',sans-serif;display:flex;justify-content:space-between;align-items:center">
    <span>📊 <b style="color:#7799bb">슬롯{pred.get('slot','')} 날짜별 북메이커 배당변동</b></span>
    <span>{trend_txt}</span>
  </div>
  <div style="font-size:.68rem;color:#334455;margin-bottom:10px">
    1 = 이긴 팀 배당변동이 진 팀보다 컸음(상승) &nbsp;|&nbsp; 0 = 이긴 팀 배당변동이 진 팀보다 작았음(하락)
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:.8rem">
    <thead>
      <tr style="border-bottom:1px solid #1a2040">
        <th style="text-align:left;color:#445566;padding:4px 8px;font-size:.72rem">북메이커</th>
        <th style="color:#7799bb;padding:4px 8px;font-size:.72rem">예측 &amp; 시퀀스</th>
        <th style="color:#445566;padding:4px 8px;font-size:.72rem">패턴</th>
        <th style="color:#445566;padding:4px 8px;font-size:.72rem;text-align:right">홈배당</th>
      </tr>
    </thead>
    <tbody>{bm_rows_html}</tbody>
  </table>
</div>
""", unsafe_allow_html=True)

# ── 히스토리 ─────────────────────────────────────────────
if len(log_df) > 0:
    _hist_df = log_df[log_df['prediction'] != 'PASS'].copy().reset_index(drop=True)
    date_min = _hist_df['date'].min()[:10] if len(_hist_df) > 0 else ''
    date_max = _hist_df['date'].max()[:10] if len(_hist_df) > 0 else ''
    st.markdown(
        f'<div class="section-title">📊 예측 기록 &nbsp;'
        f'<span style="color:#445566;font-size:.8rem;font-family:sans-serif">'
        f'백테스트 {date_min} ~ {date_max}</span></div>',
        unsafe_allow_html=True)

    ROWS_PER_PAGE = 10
    total_records = len(_hist_df)
    total_pages   = max(1, (total_records + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

    if 'hist_page' not in st.session_state or st.session_state.hist_page > total_pages:
        st.session_state.hist_page = 1  # 기본: 1페이지(최신)

    # ── 현재 페이지 레코드 (1=최신, last=오래된순) ───────────
    cur   = st.session_state.hist_page
    # 전체를 최신순으로 뒤집은 뒤 페이지 슬라이싱
    _hist_rev = _hist_df.iloc[::-1].reset_index(drop=True)
    start = (cur - 1) * ROWS_PER_PAGE
    end   = start + ROWS_PER_PAGE
    page_df = _hist_rev.iloc[start:end]

    for _, row in page_df.iterrows():
        correct_val = row.get('correct')
        if correct_val is None or (hasattr(correct_val, '__class__') and str(correct_val) == 'nan'):
            mark = '-'; mcls = 'hist-mark-X'
        else:
            mark = 'O' if correct_val else 'X'
            mcls = f'hist-mark-{mark}'
        pred_str   = row.get('prediction', '')
        actual_str = row.get('actual_winner', '')
        conf_str   = f"{row.get('confidence', 0):.0%}"
        st.markdown(f"""
<div class="hist-row">
  <span class="{mcls}">{mark}</span>
  <span style="color:#556688;min-width:60px">{str(row.get('date',''))[:10]}</span>
  <span style="color:#aabbdd;flex:1">{row.get('home','')} <span style="color:#334">vs</span> {row.get('away','')}</span>
  <span style="color:#7788aa">예측 <b style="color:#ccd">{pred_str}</b></span>
  <span style="color:#556688">→</span>
  <span style="color:#7788aa">실제 <b style="color:#ccd">{actual_str}</b></span>
  <span style="color:#445566">신뢰도 {conf_str}</span>
</div>""", unsafe_allow_html=True)

    # ── 페이지 버튼 (1행, 화면 폭에 맞게 균등 분배) ──────────
    btn_cols = st.columns(total_pages)
    for i, col in enumerate(btn_cols):
        p = i + 1
        label = f'**{p}**' if p == st.session_state.hist_page else str(p)
        with col:
            if st.button(label, key=f'hist_p_{p}', use_container_width=True):
                st.session_state.hist_page = p
                st.rerun()

    # 오답 분석
    failed_df = _hist_df[_hist_df['correct'].apply(is_false_value)].copy()
    if len(failed_df) > 0:
        st.markdown('<div class="section-title">🔎 오답 분석</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#7788aa;font-size:.82rem;margin-bottom:10px;font-family:\'Noto Sans KR\',sans-serif">'
            '최근 오답 경기 기준으로 패턴 예측이 왜 실패했는지 추정합니다. 상세 패턴 판단문은 앞으로 검증되는 경기부터 더 정확히 남습니다.'
            '</div>',
            unsafe_allow_html=True,
        )

        fail_recent = failed_df.iloc[::-1].head(8)
        for _, row in fail_recent.iterrows():
            pred_team = parse_prediction_team(row.get('prediction', ''), row.get('home', ''), row.get('away', ''))
            actual_team = parse_actual_team(row.get('actual_winner', ''), row.get('home', ''), row.get('away', ''))
            conf = float(row.get('confidence', 0) or 0)
            ml_home = float(row.get('ml_home_prob', 0.5) or 0.5)
            ml_away = float(row.get('ml_away_prob', 0.5) or 0.5)
            reason_lines = ''.join(
                f'<div class="explain-line">• {esc(reason)}</div>'
                for reason in failure_reason(row)
            )
            st.markdown(f"""
<div class="explain-box">
  <div class="explain-title">{esc(str(row.get('date',''))[:10])} · {esc(row.get('home',''))} vs {esc(row.get('away',''))}</div>
  <div class="explain-line"><b>예측</b> {esc(pred_team)} 승 · <b>실제</b> {esc(actual_team)} 승 · <b>신뢰도</b> {conf:.0%}</div>
  <div class="explain-line"><b>ML</b> 홈 {ml_home:.0%} / 원정 {ml_away:.0%}</div>
  {reason_lines}
</div>
""", unsafe_allow_html=True)

    # 슬롯별 정확도
    st.markdown('<div class="section-title">📈 슬롯별 / 신뢰도별 정확도</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**슬롯별 정확도**")
        slot_stats = _hist_df.groupby('slot')['correct'].agg(['sum','count']).reset_index()
        slot_stats['acc'] = slot_stats['sum'] / slot_stats['count']
        for _, r in slot_stats.iterrows():
            color = "#44ddaa" if r['acc'] >= 0.6 else "#ffaa00" if r['acc'] >= 0.45 else "#ff4466"
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;font-family:'Noto Sans KR',sans-serif;font-size:.82rem">
  <span style="color:#556688;min-width:50px">SLOT {int(r['slot'])}</span>
  <div style="flex:1;background:#131330;border-radius:4px;height:8px">
    <div style="width:{r['acc']*100:.0f}%;background:{color};height:8px;border-radius:4px"></div>
  </div>
  <span style="color:{color};min-width:60px;text-align:right">{int(r['sum'])}/{int(r['count'])} ({r['acc']:.0%})</span>
</div>""", unsafe_allow_html=True)

    with c2:
        st.markdown("**신뢰도별 정확도**")
        bins   = [0, 0.6, 0.7, 0.8, 0.9, 1.01]
        labels = ['~60%','60~70%','70~80%','80~90%','90%~']
        _hist2 = _hist_df.copy()
        _hist2['conf_bin'] = pd.cut(_hist2['confidence'], bins=bins, labels=labels)
        for lbl in labels:
            b = _hist2[_hist2['conf_bin'] == lbl]
            if len(b) == 0: continue
            b_acc = b['correct'].mean()
            color = "#44ddaa" if b_acc >= 0.6 else "#ffaa00" if b_acc >= 0.45 else "#ff4466"
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;font-family:'Noto Sans KR',sans-serif;font-size:.82rem">
  <span style="color:#556688;min-width:60px">{lbl}</span>
  <div style="flex:1;background:#131330;border-radius:4px;height:8px">
    <div style="width:{b_acc*100:.0f}%;background:{color};height:8px;border-radius:4px"></div>
  </div>
  <span style="color:{color};min-width:60px;text-align:right">{int(b['correct'].sum())}/{len(b)} ({b_acc:.0%})</span>
</div>""", unsafe_allow_html=True)

# ── 푸터 ─────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;color:#2a3050;font-size:.75rem;margin-top:40px;font-family:'Noto Sans KR',sans-serif">
  KBO Prediction Engine &nbsp;|&nbsp; Pattern Analysis + RandomForest ML &nbsp;|&nbsp; 2026
</div>
""", unsafe_allow_html=True)
