import os, sys, tempfile

# Anaconda 환경에서 구버전 sklearn 충돌 방지: 로컬 .deps 우선 로드
_deps = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.deps')
if os.path.isdir(_deps) and _deps not in sys.path:
    sys.path.insert(0, _deps)

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import accuracy_score
from datetime import datetime, timedelta
import json, warnings
warnings.filterwarnings('ignore')

CSV_PATH        = 'kbo_odds.csv'
GAMES_PATH      = 'kbo_games.csv'
PRED_PATH       = 'kbo_predictions.json'
TODAY_ODDS_PATH = 'kbo_today_odds.json'
WINDOW     = 19   # 팀별 최근 N경기 참조
BM_SEQ_LEN       = 17  # 슬롯별 북메이커 배당변동 시퀀스 길이
SLOT_FAV_SEQ_LEN = 18  # 슬롯별 정배/역배 승 시퀀스 길이

# ── 패턴 분석 함수 (변경 없음) ─────────────────────────────
def find_runs(seq):
    runs = []
    cur, cnt = seq[0], 1
    for v in seq[1:]:
        if v == cur: cnt += 1
        else: runs.append((cur, cnt)); cur = v; cnt = 1
    runs.append((cur, cnt))
    return runs

def check_mirror(seq):
    n = len(seq)
    for h in range(1, n//2+1):
        if n < h*2: break
        front = seq[-h*2:-h]
        back  = seq[-h:]
        if list(back) == [1-x for x in front]:
            return h, front, back
    return None

def check_repeat_block(seq):
    n = len(seq)
    for bl in range(1, n//2+1):
        chunk = seq[:bl]
        if all(seq[i] == chunk[i % bl] for i in range(n)):
            return bl, chunk
    return None

def check_palindrome(seq):
    return list(seq) == list(reversed(seq))

def check_alternating(seq):
    return len(seq) >= 2 and all(seq[i] != seq[i+1] for i in range(len(seq)-1))

def check_block_split(seq):
    n = len(seq)
    for sp in range(1, n):
        f, b = seq[:sp], seq[sp:]
        if len(set(f))==1 and len(set(b))==1 and f[0]!=b[0]:
            return sp, f[0], b[0]
    return None

def check_tail_split_mirror(seq):
    """꼬리 분할 미러 패턴: 끝 N개를 A|B로 분할, B가 A의 미러 → 다음=A[0]
    예1: [1,1,0,0,1] 끝5개→A=[1,1,0] B=[0,1]: 01이 10의 미러 → 다음=A[0]=1
    예2: [0,0,1,1,1,0,1,1] 끝4개→A=[1,0] B=[1,1]: 미러X / 끝6개→A=[1,1,1] B=[0,1,1]: 미러X
    단방향 불균등 분할(len_a != len_b)도 허용:
      끝 A+B개를 시도, B가 A 꼬리의 미러이면 다음=A[0]
    """
    n = len(seq)
    if n < 4:
        return None, None, 0.0
    candidates = []
    # 균등 분할: A=B=half
    for half in range(2, n // 2 + 1):
        tail = seq[-(half * 2):]
        a = list(tail[:half])
        b = list(tail[half:])
        if b == [1 - x for x in a]:
            pred = a[0]
            candidates.append((pred, f'꼬리미러[{"".join(str(x) for x in a)}|{"".join(str(x) for x in b)}]→{pred}', 0.83))
    # 불균등 분할: B가 A의 끝 len(B)개의 미러
    for lb in range(2, min(6, n - 2) + 1):
        for la in range(lb, min(8, n - lb) + 1):
            a = list(seq[-(la + lb):-lb])
            b = list(seq[-lb:])
            if b == [1 - x for x in a[-lb:]]:
                pred = a[0]
                label = f'꼬리부분미러[{"".join(str(x) for x in a)}|{"".join(str(x) for x in b)}]→{pred}'
                candidates.append((pred, label, 0.80))
    if candidates:
        return candidates[-1]
    return None, None, 0.0


def check_palindrome_build(seq):
    """끝이 회문(팰린드롬) 확장 중인지 감지 → 다음값 = 대칭 위치 값
    홀수 중심: seq[c-r]==seq[c+r] 으로 끝까지 확장
    짝수 중심: seq[c-1-r]==seq[c+r] 으로 끝까지 확장 (NEW)
    """
    n = len(seq)
    if n < 4:
        return None, None, 0.0
    best = None

    # 홀수 중심
    for center in range(1, n - 1):
        rad = 0
        while center - rad >= 0 and center + rad < n:
            if seq[center - rad] == seq[center + rad]:
                rad += 1
            else:
                break
        if rad >= 2 and center + rad == n:
            left_idx = center - rad
            if left_idx >= 0:
                next_val = seq[left_idx]
                label = f'팰린드롬확장[중심{center},반경{rad},→{next_val}]'
                conf = min(0.83, 0.70 + rad * 0.03)
                if best is None or rad > best[3]:
                    best = (next_val, label, conf, rad)

    # 짝수 중심: center 사이(c-1과 c 사이)에 축
    for c in range(1, n):
        rad = 0
        while c - 1 - rad >= 0 and c + rad < n:
            if seq[c - 1 - rad] == seq[c + rad]:
                rad += 1
            else:
                break
        if rad >= 2 and c + rad == n:
            left_idx = c - 1 - rad
            if left_idx >= 0:
                next_val = seq[left_idx]
                label = f'짝수팰린드롬확장[중심{c}-{c+1},반경{rad},→{next_val}]'
                conf = min(0.83, 0.70 + rad * 0.03)
                if best is None or rad > best[3]:
                    best = (next_val, label, conf, rad)

    if best:
        return best[0], best[1], best[2]
    return None, None, 0.0


def check_alternating_pairs(seq):
    """교차 쌍 패턴: [1,1,0,0,1,...] = 11|00|11|00... 또는 00|11|00|11...
    그룹 크기 k로 분할 시 홀수 그룹=A, 짝수 그룹=B(A의 반전), 현재 그룹 내 위치로 다음값 예측
    """
    n = len(seq)
    if n < 4:
        return None, None, 0.0
    for k in range(2, min(5, n // 2) + 1):
        # 전체 시퀀스를 k 크기 그룹으로 분할 (앞에서부터)
        groups = [seq[i:i + k] for i in range(0, n - (n % k) if n % k != 0 else n, k)]
        partial = seq[len(groups) * k:] if n % k != 0 else []
        if len(groups) < 2:
            continue
        # 각 그룹이 단일 값인지 확인 (모두 0 or 모두 1)
        if not all(len(set(g)) == 1 for g in groups):
            continue
        vals = [g[0] for g in groups]
        # 홀짝 교대인지 확인
        if not all(vals[i] != vals[i + 1] for i in range(len(vals) - 1)):
            continue
        # 현재 부분 그룹 예측
        if partial:
            # 부분 그룹의 다음 값 = 같은 그룹의 첫 번째 값
            next_val = partial[0]
            label = f'교차쌍[k={k},{"".join(str(v)*k for v in vals)}|{"".join(str(x) for x in partial)}→{next_val}]'
            conf = 0.82
        else:
            # 다음 새 그룹의 첫 번째 값 = 마지막 그룹 값의 반전
            next_val = 1 - vals[-1]
            label = f'교차쌍[k={k},{"".join(str(v)*k for v in vals)}→{next_val}]'
            conf = 0.80
        return next_val, label, conf
    return None, None, 0.0


def check_tail_cyclic(seq, min_period=2, min_reps=3):
    """끝 N개가 [AB]×k 형태로 주기적 반복 → 다음 값 예측
    예: [..., 1,0,1,0,1,0,1,0] → [10]×4 → 다음=1
    예: [..., 0,1,0,1,0,1] → [01]×3 → 다음=0
    """
    n = len(seq)
    best = None
    for p in range(min_period, n // min_reps + 1):
        template = list(seq[-p:])
        reps = 0
        pos = n
        while pos - p >= 0 and list(seq[pos - p:pos]) == template:
            reps += 1
            pos -= p
        if reps >= min_reps:
            tail_len = reps * p
            next_val = template[tail_len % p]  # 다음 위치
            s_tmpl = ''.join(str(x) for x in template)
            label = f'꼬리주기[{s_tmpl}]×{reps}→{next_val}'
            conf = min(0.86, 0.72 + reps * 0.04)
            if best is None or reps > best[3]:
                best = (next_val, label, conf, reps)
    if best:
        return best[0], best[1], best[2]
    return None, None, 0.0


def check_fold_palindrome_tail(seq):
    """접기 후 나머지가 팰린드롬: [...A|flip(A)...palindrome]
    접기 위치를 찾고, 그 뒤 꼬리가 팰린드롬이면 팰린드롬의 다음 값 예측
    예: [...|01|10|1001] → 접기[01|10] + 팰린드롬[1001] → 다음=flip(1001[-1])
    """
    n = len(seq)
    best = None
    for sp in range(2, n - 3):
        for fold_len in range(2, sp + 1):
            front = list(seq[sp - fold_len:sp])
            back  = list(seq[sp:sp + fold_len])
            if len(back) < fold_len:
                continue
            if back != [1 - x for x in front]:
                continue
            rest = list(seq[sp + fold_len:])
            if len(rest) < 2:
                continue
            if rest == rest[::-1]:
                # 팰린드롬 꼬리 → 다음은 팰린드롬 반대편 진행 방향 값
                next_val = 1 - rest[-1]
                sf = ''.join(str(x) for x in front)
                sb = ''.join(str(x) for x in back)
                sr = ''.join(str(x) for x in rest)
                label = f'접기팰꼬리[{sf}|{sb}]+팰[{sr}]→{next_val}'
                conf = min(0.84, 0.72 + len(rest) * 0.02)
                if best is None or len(rest) > best[3]:
                    best = (next_val, label, conf, len(rest))
    if best:
        return best[0], best[1], best[2]
    return None, None, 0.0


def check_double_fold(seq):
    """이중 접기: [A|flip(A)|B|flip(B)] 4등분 구조
    완전 4등분: next = A[0] (새 A 시작)
    진행 중: [A|flip(A)|B|flip(B)|partial_C] → partial_C가 B와 같은 방향이면 B[len(partial)]
    """
    n = len(seq)
    best = None
    for q in range(2, n // 4 + 1):
        if 4 * q > n:
            break
        A = list(seq[:q])
        B = list(seq[q:2 * q])
        C = list(seq[2 * q:3 * q])
        D = list(seq[3 * q:4 * q])
        if B != [1 - x for x in A]:
            continue
        if D != [1 - x for x in C]:
            continue
        rest = list(seq[4 * q:])
        sa = ''.join(str(x) for x in A)
        sb = ''.join(str(x) for x in B)
        sc = ''.join(str(x) for x in C)
        sd = ''.join(str(x) for x in D)
        if not rest:
            next_val = A[0]
            label = f'이중접기[{sa}|{sb}|{sc}|{sd}]→{next_val}'
            conf = 0.84
        elif list(rest) == list(A[:len(rest)]):
            next_val = A[len(rest)] if len(rest) < q else (1 - A[0])
            sr = ''.join(str(x) for x in rest)
            label = f'이중접기[{sa}|{sb}|{sc}|{sd}]+[{sr}]→{next_val}'
            conf = 0.82
        else:
            continue
        if best is None or q > best[3]:
            best = (next_val, label, conf, q)
    if best:
        return best[0], best[1], best[2]
    return None, None, 0.0


def check_fold_mirror(seq):
    n = len(seq)
    results = []
    for sp in range(2, n-1):
        for length in range(2, sp+1):
            front = seq[sp-length:sp]
            back  = seq[sp:sp+length]
            if len(back) < length: continue
            if list(back) == [1-x for x in front]:
                tail = seq[sp+length:]
                results.append((sp-length, sp, sp+length, front, back, tail))
    return results

def check_inner_palindrome(seq):
    n = len(seq)
    results = []
    for start in range(n):
        for end in range(start+2, n+1):
            chunk = seq[start:end]
            if len(chunk) >= 2 and list(chunk) == list(reversed(chunk)):
                prefix = seq[:start]
                suffix = seq[end:]
                results.append((start, end, chunk, prefix, suffix))
    results.sort(key=lambda x: -(x[1]-x[0]))
    return results

def check_run_shape(seq):
    runs = find_runs(seq)
    lens = [r[1] for r in runs]
    if len(lens) < 2: return None
    asc   = lens == sorted(lens)
    desc  = lens == sorted(lens, reverse=True)
    peak  = lens.index(max(lens))
    mountain = (lens[:peak+1] == sorted(lens[:peak+1]) and
                lens[peak:] == sorted(lens[peak:], reverse=True) and
                0 < peak < len(lens)-1)
    vi = lens.index(min(lens))
    valley = (lens[:vi+1] == sorted(lens[:vi+1], reverse=True) and
              lens[vi:] == sorted(lens[vi:]) and
              0 < vi < len(lens)-1)
    if asc:      return 'asc', lens
    if desc:     return 'desc', lens
    if mountain: return 'mountain', lens
    if valley:   return 'valley', lens
    return None

def check_run_mirror_pattern(seq):
    """런-길이 인코딩 기반 Mirror쌍 + 팰린드롬 패턴 분할 예측
    예: [0,0,1,1,0,0,0,1,0,0,0]
      runs: [(0,2),(1,2),(0,3),(1,1),(0,3)]
      → [00|11]=Mirror쌍 + [0001000]=팰린드롬(중심=1) → 다음=1
    반환: (예측값 or None, 설명 or None, 점수)
    """
    n = len(seq)
    if n < 4:
        return None, None, 0.0

    # Run-length encoding
    runs = []
    i = 0
    while i < n:
        j = i
        while j < n and seq[j] == seq[i]:
            j += 1
        runs.append((seq[i], j - i))
        i = j

    rn = len(runs)
    if rn < 2:
        return None, None, 0.0

    vals = [r[0] for r in runs]
    lens = [r[1] for r in runs]

    def runs_str(rs):
        return ''.join(''.join([str(r[0])] * r[1]) for r in rs)

    candidates = []

    # ── 1. 앞 K쌍이 Mirror → 나머지 구조 분석 ──────────────────
    for k in range(1, rn // 2 + 1):
        if 2 * k > rn:
            break
        head = runs[:k]
        next_k = runs[k:2 * k]

        is_mirror = all(
            head[i][0] != next_k[i][0] and head[i][1] == next_k[i][1]
            for i in range(k)
        )
        if not is_mirror:
            continue

        mirror_runs = runs[:2 * k]
        rest = runs[2 * k:]

        if not rest:
            # 전체 Mirror쌍 완성 → 새 사이클 첫 값
            nv = vals[0]
            candidates.append((
                nv,
                f'런분할 [{runs_str(mirror_runs)}]=Mirror완성 → 새사이클={nv}',
                0.80
            ))
            break

        rest_lens = [r[1] for r in rest]
        rest_vals = [r[0] for r in rest]
        rest_is_pal = rest_lens == rest_lens[::-1]

        if rest_is_pal:
            center = rest_vals[len(rest_vals) // 2]
            nv = center
            candidates.append((
                nv,
                (f'런분할 [{runs_str(mirror_runs)}]=Mirror'
                 f' + [{runs_str(rest)}]=팰린드롬(중심={center}) → 다음={nv}'),
                0.85
            ))
        else:
            # Mirror쌍 있고 나머지 비팰린드롬 → 나머지 끝값의 반대
            nv = 1 - rest_vals[-1]
            candidates.append((
                nv,
                (f'런분할 [{runs_str(mirror_runs)}]=Mirror'
                 f' + [{runs_str(rest)}] → 다음={nv}'),
                0.72
            ))

    # ── 2. 전체 또는 끝 구간이 팰린드롬 (Mirror쌍 없이) ───────────
    for start in range(rn - 1, -1, -1):
        sub_lens = lens[start:]
        if len(sub_lens) < 3:
            continue
        if sub_lens != sub_lens[::-1]:
            continue
        sub_vals = vals[start:]
        sub_runs = runs[start:]
        center = sub_vals[len(sub_vals) // 2]
        nv = center
        prefix = runs[:start]
        if start == 0:
            desc = f'런분할 [{runs_str(runs)}]=전체팰린드롬(중심={center}) → 다음={nv}'
        else:
            desc = (f'런분할 [{runs_str(prefix)}]'
                    f' + [{runs_str(sub_runs)}]=팰린드롬(중심={center}) → 다음={nv}')
        candidates.append((nv, desc, 0.78))
        break

    if not candidates:
        return None, None, 0.0

    best = max(candidates, key=lambda x: x[2])
    return best[0], best[1], best[2]

def check_staircase_pattern(seq):
    """런 길이가 등차수열(계단식)인 패턴 감지
    예: 111001 → runs [(1,3),(0,2),(1,1)] → 길이 [3,2,1] (Δ-1) → 다음 run=(0,0) 완성 → 새 사이클 시작=1
    예: 000110 → runs [(0,3),(1,2),(0,1)] → 길이 [3,2,1] (Δ-1) → 다음=0
    """
    runs = find_runs(seq)
    if len(runs) < 3:
        return None, None, 0.0
    lens = [r[1] for r in runs]
    diffs = [lens[i+1] - lens[i] for i in range(len(lens)-1)]
    if len(set(diffs)) != 1 or diffs[0] == 0:
        return None, None, 0.0
    step = diffs[0]
    next_len = lens[-1] + step
    s = ''.join(str(x) for x in seq)
    if next_len <= 0:
        # 계단 완성 → 새 사이클 시작값 = 첫 런 값
        nv = runs[0][0]
        return nv, f'계단식[{s}] 런={lens}(Δ{step:+d}) → 사이클완성→{nv}', 0.80
    nv = 1 - runs[-1][0]
    return nv, f'계단식[{s}] 런={lens}(Δ{step:+d}) → 다음런={nv}×{next_len}', 0.82

def check_run_length_balancer(seq):
    """런-길이 밸런서: 직전 런(N_prev)과 현재 런(N_cur)의 길이를 비교
    N_cur < N_prev 이면 현재값이 계속돼 균형을 맞출 것으로 예측
    예: [...,1,1,1,0,0] → N₁=3 > N₀=2, 부족=1 → 0 예측
    예: [...,0,0,0,0,0,1,1,1] → N₀=5 > N₁=3, 부족=2 → 1 예측
    """
    runs = find_runs(seq)
    if len(runs) < 2:
        return None, None, 0.0
    prev_val, prev_len = runs[-2]
    cur_val,  cur_len  = runs[-1]
    if cur_len < prev_len:
        deficit = prev_len - cur_len
        s = ''.join(str(x) for x in seq)
        desc = (f'런밸런서[{prev_val}×{prev_len}→{cur_val}×{cur_len}'
                f', 부족={deficit}→{cur_val}]')
        score = min(0.80, 0.62 + deficit * 0.05)
        return cur_val, desc, score
    return None, None, 0.0


def _wilson_lower(hits, total, z=1.96):
    """Wilson score lower bound (95% CI). 작은 표본의 비율 과신 방지.
    표본이 적을수록 보수적인 값 반환 (예: 2/2 → 0.66 not 1.0)."""
    if total == 0:
        return 0.0
    p = hits / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = p + z2 / (2.0 * total)
    margin = z * ((p * (1 - p) + z2 / (4.0 * total)) / total) ** 0.5
    return max(0.0, (center - margin) / denom)

# P3: 히스토리 매칭 최소 표본 (저표본 과신 차단)
HISTORY_MIN_MATCHES = 5  # 이전 2 → 5로 상향

def check_history_match(seq, full_history):
    """현재 seq tail을 전체 과거 히스토리에서 검색해 다음 값 예측
    - exact match: 히스토리에서 seq와 동일한 구간 찾기 → 그 다음 값
    - complement match: seq의 비트반전을 검색 → 예측값도 반전
    P3 적용: 최소 매치 수 5건 이상 + Wilson Lower Bound로 score 산출
    반환: (예측값 or None, 설명 or None, 점수)
    """
    clean_h = [x for x in full_history if x in (0, 1)]
    n = len(seq)
    if len(clean_h) <= n or n < 3:
        return None, None, 0.0

    s = ''.join(str(x) for x in seq)

    # Exact match
    matches = []
    for i in range(len(clean_h) - n):
        if clean_h[i:i+n] == list(seq):
            matches.append(clean_h[i+n])

    label = '히스토리조회'
    complement = False

    if not matches:
        comp = [1 - x for x in seq]
        for i in range(len(clean_h) - n):
            if clean_h[i:i+n] == comp:
                matches.append(1 - clean_h[i+n])
        if matches:
            complement = True
            label = '보수조회'

    # P3: 최소 표본 게이트 — 2~4건 매칭의 과신 방지
    if len(matches) < HISTORY_MIN_MATCHES:
        return None, None, 0.0

    ones = sum(matches)
    zeros = len(matches) - ones
    nv = 1 if ones > zeros else 0
    majority = max(ones, zeros)
    vote_ratio = majority / len(matches)
    # P3: Wilson Lower Bound (95% CI) 사용 — 표본 적을수록 보수적
    lb = _wilson_lower(majority, len(matches))
    if lb < 0.55:
        return None, None, 0.0
    comp_tag = '(보수)' if complement else ''
    desc = f'{label}{comp_tag}[{s}] {len(matches)}회매칭→{nv}({vote_ratio:.0%}, LB={lb:.0%})'
    score = min(0.84, 0.55 + lb * 0.35)  # LB 기반 동적 점수
    return nv, desc, score

def check_rolling_momentum(seq):
    """최근 여러 window의 1/0 비율이 같은 방향으로 쏠리는지 확인
    이미 있는 연속/런/반복 패턴이 아니라, 최근 구간별 다수 방향 자체를 신호로 사용한다.
    """
    n = len(seq)
    if n < 5:
        return None, None, 0.0

    windows = [w for w in (5, 7, 10, 15, 20) if w <= n]
    signals = []
    for w in windows:
        tail = seq[-w:]
        ones = sum(tail)
        ratio = ones / w
        if ratio >= 0.65:
            signals.append((1, w, ratio))
        elif ratio <= 0.35:
            signals.append((0, w, 1 - ratio))

    if len(signals) < 2:
        return None, None, 0.0

    s1 = [x for x in signals if x[0] == 1]
    s0 = [x for x in signals if x[0] == 0]
    side = 1 if len(s1) > len(s0) else 0
    chosen = s1 if side == 1 else s0
    if len(chosen) < 2:
        return None, None, 0.0

    avg_strength = sum(x[2] for x in chosen) / len(chosen)
    win_txt = ','.join(str(x[1]) for x in chosen)
    desc = f'롤링모멘텀[{win_txt}] → {side}({avg_strength:.0%})'
    score = min(0.74, 0.55 + avg_strength * 0.25)
    return side, desc, score

def check_similarity_match(seq, full_history):
    """완전일치가 아닌 유사 패턴 매칭
    최근 tail과 과거 구간의 Hamming 유사도가 높을 때 다음 값을 다수결로 예측한다.
    """
    clean_h = [x for x in full_history if x in (0, 1)]
    n = len(seq)
    if len(clean_h) < 12 or n < 5:
        return None, None, 0.0

    best = (None, None, 0.0)
    for tail_len in range(min(n, 10), 4, -1):
        tail = list(seq[-tail_len:])
        min_same = max(4, int(np.ceil(tail_len * 0.75)))
        matches = []

        for i in range(len(clean_h) - tail_len):
            cand = clean_h[i:i + tail_len]
            same = sum(1 for a, b in zip(tail, cand) if a == b)
            if same >= min_same:
                matches.append((clean_h[i + tail_len], same / tail_len))

        # P3: 최소 표본 5건 (이전 4건 → 5건)
        if len(matches) < 5:
            continue

        ones = sum(v for v, _ in matches)
        zeros = len(matches) - ones
        nv = 1 if ones > zeros else 0
        majority = max(ones, zeros)
        vote_ratio = majority / len(matches)
        # P3: Wilson Lower Bound 적용
        lb = _wilson_lower(majority, len(matches))
        if lb < 0.55:
            continue

        avg_sim = sum(sim for _, sim in matches) / len(matches)
        score = min(0.80, 0.55 + lb * 0.25 + avg_sim * 0.05)
        desc = f'유사매칭[{tail_len}] {len(matches)}회 sim{avg_sim:.0%}→{nv}({vote_ratio:.0%}, LB={lb:.0%})'
        if score > best[2]:
            best = (nv, desc, score)

    return best

def check_meta_alternating(seq, full_history=None):
    """계단식↔짝맞춤 교대 메타패턴 감지

    현재 seq를 S(계단식)/P(짝맞춤) 구간으로 분할:
      3분할: S→P→S 또는 P→S→P → 중간 타입이 다음에도 반복 (score 0.85)
      2분할: S→P 또는 P→S → 처음 타입이 다음에 재등장 (score 0.80)
    마지막 구간의 반대 타입 예측 로직을 seq에 적용해 다음 값 반환
    """
    n = len(seq)
    if n < 8:
        return None, None, 0.0

    def _classify(b):
        if len(b) < 4:
            return None, 0.0
        _, _, s_sc = check_staircase_pattern(b)
        if s_sc >= 0.78:
            return 'S', s_sc
        _, _, rm_sc = check_run_mirror_pattern(b)
        if rm_sc >= 0.78:
            return 'P', rm_sc
        rl = [r[1] for r in find_runs(b)]
        if len(rl) >= 3 and rl == rl[::-1]:
            return 'P', 0.75
        return None, 0.0

    clean_h = [x for x in (full_history or []) if x in (0, 1)]

    # ── 3분할: S→P→S 또는 P→S→P ──────────────────────────────
    found3 = None
    for i in range(4, n - 8):
        t1, sc1 = _classify(seq[:i])
        if t1 is None:
            continue
        for j in range(i + 4, n - 4):
            t2, sc2 = _classify(seq[i:j])
            t3, sc3 = _classify(seq[j:])
            if t2 and t3 and t1 != t2 and t2 != t3 and t1 == t3:
                # (chain, next_t, avg_sc, split_j)
                found3 = ([t1, t2, t3], t2, (sc1 + sc2 + sc3) / 3, j)
                break
        if found3:
            break

    if found3:
        chain, next_t, avg_sc, split_j = found3
        last_seg = list(seq[split_j:])
        last_t   = chain[-1]   # 마지막 구간 타입
        base     = min(0.85, avg_sc + 0.03)
    else:
        # ── 2분할: S→P 또는 P→S ───────────────────────────────
        found2 = None
        for i in range(4, n - 4):
            t1, sc1 = _classify(seq[:i])
            t2, sc2 = _classify(seq[i:])
            if t1 and t2 and t1 != t2:
                found2 = ([t1, t2], t1, (sc1 + sc2) / 2, i)
                break
        if not found2:
            return None, None, 0.0
        chain, next_t, avg_sc, split_i = found2
        last_seg = list(seq[split_i:])
        last_t   = chain[-1]
        base     = min(0.80, avg_sc + 0.02)

    chain_str = '→'.join(chain) + f'→[{next_t}]'

    # 마지막 구간의 타입 예측 로직을 last_seg에 적용
    if last_t == 'S':
        nv, d, sc = check_staircase_pattern(last_seg)
    else:  # P
        nv, d, sc = check_run_mirror_pattern(last_seg)
        if nv is None and clean_h:
            nv, d, sc = check_history_match(last_seg, clean_h)

    if nv is None:
        return None, None, 0.0
    return nv, f'교대메타[{chain_str}] {d}', base

def tail_recommendation(tail):
    if not tail: return None, None
    s = ''.join(str(x) for x in tail)
    if check_alternating(tail) and len(tail) >= 2:
        return 1-tail[-1], f'꼬리[{s}]=10101→{1-tail[-1]}'
    mir = check_mirror(tail)
    if mir:
        h, front, back = mir
        rec = 1 - tail[-h*2] if len(tail) > h*2 else 1-tail[0]
        return rec, f'꼬리[{s}]=Mirror→{rec}'
    rb = check_repeat_block(tail)
    if rb:
        bl, chunk = rb
        rec = chunk[len(tail) % bl]
        return rec, f'꼬리[{s}]=반복→{rec}'
    bs = check_block_split(tail)
    if bs:
        _, f_val, _ = bs
        return f_val, f'꼬리[{s}]=연속블록→{f_val}'
    return None, f'꼬리[{s}]=불규칙'

def label_part(part):
    s = ''.join(str(x) for x in part)
    rb  = check_repeat_block(part)
    bs  = check_block_split(part)
    alt = check_alternating(part)
    pal = check_palindrome(part)
    mir = check_mirror(part)
    if rb:    return f'[{s}]=반복[{"".join(str(x) for x in rb[1])}]×{len(part)//rb[0]}', 'rep', rb
    elif bs:  return f'[{s}]=연속블록', 'blk', bs
    elif alt: return f'[{s}]=10101', 'alt', None
    elif pal: return f'[{s}]=대칭', 'pal', None
    elif mir: return f'[{s}]=Mirror', 'mir', mir
    else:     return f'[{s}]', None, None

def next_from_last(part, kind, info):
    if kind == 'rep':
        bl, chunk = info
        return chunk[len(part) % bl]
    elif kind == 'blk':
        _, f_val, _ = info
        return f_val
    elif kind == 'alt':
        return 1 - part[-1]
    elif kind == 'pal':
        return 1 - part[-1]
    elif kind == 'mir':
        return 1 - part[0]
    return None

def segment_patterns(seq):
    n = len(seq)
    found = []
    for i in range(2, n-1):
        parts = [seq[:i], seq[i:]]
        labeled = [label_part(p) for p in parts]
        named = sum(1 for _,k,_ in labeled if k is not None)
        if named >= 1:
            desc = ' + '.join(l for l,_,_ in labeled)
            _, last_kind, last_info = labeled[-1]
            rec = next_from_last(parts[-1], last_kind, last_info)
            found.append((desc, parts[-1], rec))
    for i in range(2, n-3):
        for j in range(i+2, n-1):
            parts = [seq[:i], seq[i:j], seq[j:]]
            labeled = [label_part(p) for p in parts]
            named = sum(1 for _,k,_ in labeled if k is not None)
            if named >= 2:
                desc = ' + '.join(l for l,_,_ in labeled)
                _, last_kind, last_info = labeled[-1]
                rec = next_from_last(parts[-1], last_kind, last_info)
                found.append((desc, parts[-1], rec))
    found.sort(key=lambda x: -x[0].count('='))
    return found[:5]

def analyze_pattern(seq, full_history=None):
    n = len(seq)
    s = ''.join(str(x) for x in seq)
    candidates = []

    if len(set(seq)) == 1:
        candidates.append({'type':'전체연속',
                           'desc':f'[{s}] {seq[0]}이 {n}번 연속',
                           'rec': 1-seq[0], 'score': 0.70})

    if check_alternating(seq) and n >= 3:
        candidates.append({'type':'10101',
                           'desc':f'[{s}] 교대 패턴',
                           'rec': 1-seq[-1], 'score': 0.50, 'pass': True})

    rb = check_repeat_block(seq)
    if rb:
        bl, chunk = rb
        next_val = chunk[len(seq) % bl]
        candidates.append({'type':'반복블록',
                           'desc':f'[{s}] [{"".join(str(x) for x in chunk)}]×{n//bl} 반복',
                           'rec': next_val, 'score': 0.80})

    if check_palindrome(seq) and n > 2:
        candidates.append({'type':'대칭',
                           'desc':f'[{s}] 좌우 대칭',
                           'rec': None, 'score': 0.60})

    bs = check_block_split(seq)
    if bs:
        sp, f_val, b_val = bs
        f_len, b_len = sp, n-sp
        if f_len == b_len:
            candidates.append({'type':'연속블록대칭',
                               'desc':f'[{s}] {f_val}×{f_len}|{b_val}×{b_len}',
                               'rec': f_val, 'score': 0.82})
        else:
            candidates.append({'type':'연속블록',
                               'desc':f'[{s}] {f_val}×{f_len}|{b_val}×{b_len}',
                               'rec': b_val, 'score': 0.72})

    fold_results = check_fold_mirror(seq)
    for (start, sp, end, front, back, tail) in fold_results:
        front_s = ''.join(str(x) for x in front)
        back_s  = ''.join(str(x) for x in back)
        tail_rec, tail_desc = tail_recommendation(list(tail))
        if tail_rec is not None:
            candidates.append({'type':'반접기+꼬리',
                               'desc':f'[{s}] 반접기[{front_s}|{back_s}] + {tail_desc}',
                               'rec': tail_rec, 'score': 0.78})
            break

    inner_pals = check_inner_palindrome(seq)
    for (start, end, chunk, prefix, suffix) in inner_pals:
        chunk_s = ''.join(str(x) for x in chunk)
        if len(chunk) < 2: continue
        tail_rec, tail_desc = tail_recommendation(list(suffix))
        if tail_rec is not None:
            candidates.append({'type':'중간대칭+꼬리',
                               'desc':f'[{s}] 중간대칭[{chunk_s}] + {tail_desc}',
                               'rec': tail_rec, 'score': 0.75})
            break
        elif not suffix:
            rec = 1 - chunk[-1]
            candidates.append({'type':'중간대칭',
                               'desc':f'[{s}] 중간대칭[{chunk_s}]→다음{rec}',
                               'rec': rec, 'score': 0.72})
            break

    tc_val, tc_desc, tc_score = check_tail_cyclic(seq)
    if tc_val is not None:
        candidates.append({'type':'꼬리주기',
                           'desc': tc_desc,
                           'rec':  tc_val,
                           'score': tc_score})

    fp_val, fp_desc, fp_score = check_fold_palindrome_tail(seq)
    if fp_val is not None:
        candidates.append({'type':'접기팰꼬리',
                           'desc': fp_desc,
                           'rec':  fp_val,
                           'score': fp_score})

    run_mir_val, run_mir_desc, run_mir_score = check_run_mirror_pattern(seq)
    if run_mir_val is not None:
        candidates.append({'type':'런분할',
                           'desc': run_mir_desc,
                           'rec':  run_mir_val,
                           'score': run_mir_score})

    rlb_val, rlb_desc, rlb_score = check_run_length_balancer(seq)
    if rlb_val is not None:
        candidates.append({'type':'런밸런서',
                           'desc': rlb_desc,
                           'rec':  rlb_val,
                           'score': rlb_score})

    roll_val, roll_desc, roll_score = check_rolling_momentum(seq)
    if roll_val is not None:
        candidates.append({'type':'롤링모멘텀',
                           'desc': roll_desc,
                           'rec':  roll_val,
                           'score': roll_score})

    if full_history is not None:
        # 다양한 tail 길이로 히스토리 조회 (최소 4, 최대 현재 seq 길이)
        best_hm = (None, None, 0.0)
        for tail_len in range(min(n, 12), 3, -1):
            tail_seq = seq[-tail_len:]
            hm_val, hm_desc, hm_score = check_history_match(tail_seq, full_history)
            if hm_val is not None and hm_score > best_hm[2]:
                best_hm = (hm_val, hm_desc, hm_score)
                break  # 가장 긴 tail에서 매칭된 것 우선
        if best_hm[0] is not None:
            candidates.append({'type':'짝맞춤',
                               'desc': best_hm[1],
                               'rec':  best_hm[0],
                               'score': best_hm[2]})

        sim_val, sim_desc, sim_score = check_similarity_match(seq, full_history)
        if sim_val is not None:
            candidates.append({'type':'유사매칭',
                               'desc': sim_desc,
                               'rec':  sim_val,
                               'score': sim_score})

    segs = segment_patterns(seq)

    if not candidates:
        seg_rec = None
        seg_desc = None
        for desc, last_part, rec in segs:
            if rec is not None:
                seg_rec = rec; seg_desc = desc; break
        if seg_rec is not None:
            return {'type':'분할패턴',
                    'desc':f'[{s}] 분할: {seg_desc}',
                    'rec': seg_rec, 'score': 0.70, 'pass': False,
                    'segments': [d for d,_,_ in segs]}
        return {'type':'불규칙',
                'desc':f'[{s}] 불규칙 → 패스',
                'rec': None, 'score': 0.0, 'pass': True,
                'segments': [d for d,_,_ in segs]}

    best = max(candidates, key=lambda x: x['score'])
    best.setdefault('pass', False)
    best['segments'] = [d for d,_,_ in segs]
    if best['type'] == '10101':
        best['pass'] = True
    return best


# ── 데이터 로드 ───────────────────────────────────────────
from datetime import datetime as _dt, timedelta as _td

def normalize_date(raw):
    """'Today, 25 Apr' / 'Yesterday, 24 Apr' / '21 Apr 2026' → 'YYYY-MM-DD'"""
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - _td(days=1)).strftime('%Y-%m-%d')
    # 'DD Mon YYYY' 또는 'DD Mon YYYY - ...' 형태
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s  # 변환 불가 시 원본 반환

print('데이터 로드 중...')

# 오늘 개장 배당 로드 (Next Matches에서 수집된 실시간 배당)
_today_odds = {}
if os.path.exists(TODAY_ODDS_PATH):
    with open(TODAY_ODDS_PATH, encoding='utf-8') as _f:
        _today_odds = json.load(_f)
    print(f'오늘 개장 배당 로드: {len(_today_odds)}경기')

def get_today_odds(slot, home, away, pred_date):
    """kbo_today_odds.json에서 해당 경기의 실제 개장 배당 반환"""
    try:
        key = f"{pred_date}|{int(slot)}|{home}|{away}"
    except (ValueError, TypeError):
        return None
    return _today_odds.get(key)

df = pd.read_csv(CSV_PATH)
df['date'] = df['date'].apply(normalize_date)
df['direction'] = df['consensus'].map({'home': 1, 'away': 0})
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)
df = df.sort_values(['date_order', 'slot', 'bookmaker']).reset_index(drop=True)

# ── 경기 단위 집계 (북메이커 전체 기준) ─────────────────────
meta = df.drop_duplicates('match_id')[
    ['match_id', 'date', 'date_order', 'slot',
     'home', 'away', 'winner', 'winner_is_home']
].set_index('match_id')

bm_agg = df.groupby('match_id').agg(
    bm_count      = ('bookmaker',   'count'),
    home_pct      = ('consensus',   lambda x: (x == 'home').mean()),   # 홈 지지 북메이커 비율
    avg_home_odds = ('home_close',  'mean'),
    avg_away_odds = ('away_close',  'mean'),
    std_home_odds = ('home_close',  'std'),
    std_away_odds = ('away_close',  'std'),
)

game_df = meta.join(bm_agg).reset_index().sort_values('date_order').reset_index(drop=True)

# 다수결 컨센서스 (50% 초과면 home)
game_df['consensus']     = game_df['home_pct'].apply(lambda p: 'home' if p > 0.5 else 'away')
# 컨센서스 강도: 0.5~1.0 → 얼마나 강한 쏠림인지
game_df['consensus_str'] = (game_df['home_pct'] - 0.5).abs() * 2   # 0=중립, 1=만장일치
# 컨센서스가 이긴 경우
game_df['consensus_win'] = (
    ((game_df['consensus'] == 'home') &  game_df['winner_is_home'].fillna(False).astype(bool)) |
    ((game_df['consensus'] == 'away') & ~game_df['winner_is_home'].fillna(False).astype(bool))
).astype(int)

# ── kbo_games.csv fallback 병합 ────────────────────────────
# OddsPortal 상세 배당이 아직 없는 완료 경기도 팀승패/ML에는 반영한다.
# 배당/정배 관련 시퀀스는 bm_count=0 행을 제외해서 오염을 막는다.
if os.path.exists(GAMES_PATH):
    _gdf = pd.read_csv(GAMES_PATH)
    _today = datetime.today().strftime('%Y-%m-%d')
    for _d in sorted(_gdf['date'].dropna().astype(str).unique()):
        if _d not in date_map:
            date_map[_d] = -1  # 임시값; 아래에서 재정렬
    # 모든 날짜를 시간순으로 재정렬하여 date_order 재할당
    # (kbo_games.csv에만 있는 날짜가 kbo_odds.csv 날짜 사이에 끼어야 함)
    all_sorted_dates = sorted(date_map.keys())
    date_map = {d: i for i, d in enumerate(all_sorted_dates)}
    df['date_order'] = df['date'].map(date_map)
    game_df['date_order'] = game_df['date'].map(date_map)

    _existing_slots = set(zip(game_df['date'], game_df['slot'].apply(lambda x: str(float(x)))))
    _candidates = _gdf[
        (_gdf['date'] < _today) &
        _gdf['slot'].notna()
    ].copy()
    _fallback_rows = []
    for _, r in _candidates.iterrows():
        key = (r['date'], str(float(r['slot'])))
        if key in _existing_slots:
            continue
        is_postp = pd.isna(r.get('winner')) or str(r.get('winner')).strip() == 'Postp'
        winner_is_home = float('nan') if (is_postp or pd.isna(r.get('winner_is_home'))) else bool(r['winner'] == r['home'])
        _fallback_rows.append({
            'match_id':      f'games_{r["date"]}_s{int(r["slot"])}',
            'date':          r['date'],
            'date_order':    date_map.get(r['date'], -1),
            'slot':          float(r['slot']),
            'home':          r['home'],
            'away':          r['away'],
            'winner':        'Postp' if is_postp else r['winner'],
            'winner_is_home': winner_is_home,
            'bm_count':      0,
            'home_pct':      float('nan'),
            'avg_home_odds': float('nan'),
            'avg_away_odds': float('nan'),
            'std_home_odds': float('nan'),
            'std_away_odds': float('nan'),
            'consensus':     'Postp' if is_postp else 'unknown',
            'consensus_str': float('nan'),
            'consensus_win': float('nan'),
        })
    if _fallback_rows:
        _pdf = pd.DataFrame(_fallback_rows)
        game_df = pd.concat([game_df, _pdf], ignore_index=True)\
                    .sort_values(['date_order', 'slot']).reset_index(drop=True)
        n_done = int((_pdf['winner'] != 'Postp').sum())
        n_postp = int((_pdf['winner'] == 'Postp').sum())
        print(f'kbo_games fallback 병합: 완료 {n_done}개 / Postp {n_postp}개')

print(f'데이터 로드: {len(df)}행 | {len(date_map)}일치 | {len(game_df)}경기')


# ── 팀 기반 시퀀스 함수 ───────────────────────────────────
def get_team_triple_seq(team, before_date_order, window=WINDOW):
    """팀 최근 경기 4개 시퀀스 반환:
    - direction    : 북메이커 다수결로 팀이 정배(1) or 역배(0)
    - bm_agreement : 북메이커 의견 일치(1=강한 쏠림≥70%) or 분산(0=분열<70%)
    - fav_win      : 정배팀 승(1) or 역배팀 승(0)
    - team_win     : 해당 팀 승(1) or 패(0)
    """
    mask = (
        ((game_df['home'] == team) | (game_df['away'] == team)) &
        (game_df['date_order'] < before_date_order) &
        (game_df['winner'] != 'Postp')   # Postp 경기는 팀 시퀀스에서 제외
    )
    recent_all = game_df[mask].sort_values('date_order')
    recent_bm = recent_all[recent_all['bm_count'] > 0] if 'bm_count' in recent_all.columns else recent_all
    recent = recent_bm.tail(window)
    direction_seq, agree_seq, fav_win_seq, team_win_seq = [], [], [], []
    for _, r in recent.iterrows():
        is_fav = (
            (r['consensus'] == 'home' and r['home'] == team) or
            (r['consensus'] == 'away' and r['away'] == team)
        )
        direction_seq.append(1 if is_fav else 0)
        # 강한 쏠림: 북메이커 70% 이상 동일 방향이면 1 (consensus_str >= 0.4)
        cstr = r.get('consensus_str', 0)
        agree_seq.append(1 if (cstr and not pd.isna(cstr) and cstr >= 0.4) else 0)
        cw = r['consensus_win']
        fav_win_seq.append(int(cw) if not pd.isna(cw) else 0)
    for _, r in recent_all.tail(window).iterrows():
        team_win_seq.append(1 if r['winner'] == team else 0)
    return direction_seq, agree_seq, fav_win_seq, team_win_seq

def get_slot_fav_win_seq(slot, before_date_order, window=SLOT_FAV_SEQ_LEN):
    """해당 슬롯(N번째 경기)의 날짜별 정배승(1)/역배승(0) 시퀀스
    Ex) 2번째 경기: 20일→1, 21일→0, 22일→1, 23일→1, 24일→1 → 오늘 예측
    """
    bm_ok = (game_df['bm_count'] > 0) if 'bm_count' in game_df.columns else pd.Series(True, index=game_df.index)
    mask = (
        (game_df['slot'] == slot) &
        (game_df['date_order'] < before_date_order) &
        (game_df['winner'] != 'Postp') &
        bm_ok
    )
    recent = game_df[mask].sort_values('date_order').tail(window)
    pairs = [(int(cw), dt) for cw, dt in zip(recent['consensus_win'], recent['date']) if not pd.isna(cw)]
    if pairs:
        seqs, dates = zip(*pairs)
        return list(seqs), list(dates)
    return [], []

def get_team_win_seq(team, before_date_order, window=WINDOW):
    _, _, _, team_win = get_team_triple_seq(team, before_date_order, window)
    return team_win

def get_team_fav_seq(team, before_date_order, window=WINDOW):
    direction, _, _, _ = get_team_triple_seq(team, before_date_order, window)
    return direction

def make_feat_team(home, away, before_date_order):
    """홈팀 + 원정팀 시퀀스 피처 벡터 (6 × WINDOW)"""
    def pad(seq):
        return [-1] * (WINDOW - len(seq)) + seq

    h_dir, h_agr, h_fav, hw = get_team_triple_seq(home, before_date_order)
    a_dir, a_agr, a_fav, aw = get_team_triple_seq(away, before_date_order)
    return pad(hw) + pad(aw) + pad(h_dir) + pad(a_dir) + pad(h_agr) + pad(a_agr)

def seq_str(seq):
    return ''.join(str(x) for x in seq) if seq else '-'

def preprocess_seq(seq):
    """P 제거, 끝의 연속 N/F 제거 후 0/1만 추출"""
    result = [v for v in seq if v != 'P']
    while result and result[-1] in ('N', 'F'):
        result.pop()
    return [x for x in result if x in (0, 1)]

def preprocess_seq_p_boundary(seq):
    """P를 세그먼트 경계로 처리 → (recent_segment, full_history)
    P는 연기 경기 표시로, 이전 시즌/기간과의 구분선으로 취급.
    recent_segment: 마지막 P 이후 구간 (0/1만, trailing N/F 제거)
    full_history: 전체 구간 연결 (older→recent 순)
    """
    segments = []
    current = []
    for v in seq:
        if v == 'P':
            s = current[:]
            while s and s[-1] in ('N', 'F'):
                s.pop()
            cleaned = [x for x in s if x in (0, 1)]
            if cleaned:
                segments.append(cleaned)
            current = []
        else:
            current.append(v)
    # 마지막 세그먼트
    s = current[:]
    while s and s[-1] in ('N', 'F'):
        s.pop()
    cleaned = [x for x in s if x in (0, 1)]
    if cleaned:
        segments.append(cleaned)

    if not segments:
        return [], []
    recent = segments[-1]
    full   = [x for seg in segments for x in seg]
    return recent, full

def pat_rec(seq, full_history=None):
    """시퀀스 패턴 분석 → (추천값 or None, 설명문자열)"""
    if len(seq) < 3:
        return None, '데이터 부족'
    pa = analyze_pattern(seq, full_history=full_history)
    rec = pa['rec'] if not pa.get('pass') else None
    return rec, pa['desc']

def _extract_pattern_type(desc):
    """설명 문자열에서 패턴 유형명 추출"""
    for keyword in ['꼬리미러', '꼬리부분미러', '팰린드롬확장', '짝수팰린드롬확장', '교차쌍', 'Mirror', 'Fold+꼬리',
                    '꼬리주기', '접기팰꼬리', '이중접기',
                    '반복블록', '블록분할', '교차', '연속', '계단식', '런분할', '분할:', '짝맞춤:', '롤링모멘텀']:
        if keyword in desc:
            return keyword
    return desc.split('[')[0].split('(')[0][:16]


# P2: 무작위 시퀀스 기반 발화율 (information_factor = 1 - random_rate)
# pattern_random_rate.json 측정값. 발화율 높을수록 정보량 낮음 → 가중치 페널티
_RANDOM_RATE = {
    '교차': 0.0000, '연속': 0.0000, '반복': 0.0034, '블록분할': 0.0001,
    '교차쌍': 0.0005, '꼬리주기': 0.0798,
    '런밸런서': 0.3292, '꼬리부분미러': 0.4135, '꼬리미러': 0.4135,
    '롤링모멘텀': 0.4361, '접기팰꼬리': 0.5693,
    '런분할': 0.6549, '팰린드롬확장': 0.9101, 'Fold+꼬리': 0.9831,
}

# P5: 적응형 가중치 — pattern_accuracy.json에서 누적 적중률 로드
# 라플라스 스무딩 + 발화 횟수 < MIN_FIRES이면 하드코딩값과 블렌딩
_PATTERN_ACC_PATH = 'pattern_accuracy.json'
_ADAPTIVE_MIN_FIRES = 20  # 이 미만이면 하드코딩 비중 유지
_PATTERN_ACC_CACHE = None

def _load_pattern_accuracy():
    global _PATTERN_ACC_CACHE
    if _PATTERN_ACC_CACHE is not None:
        return _PATTERN_ACC_CACHE
    if os.path.exists(_PATTERN_ACC_PATH):
        with open(_PATTERN_ACC_PATH, encoding='utf-8') as _f:
            _PATTERN_ACC_CACHE = json.load(_f)
    else:
        _PATTERN_ACC_CACHE = {}
    return _PATTERN_ACC_CACHE

def _adaptive_factor(ptype, hardcoded_score):
    """누적 적중률을 라플라스 스무딩 → 하드코딩값과 블렌딩 → 배율 반환.
    50%를 기준으로 actual_acc/0.5 비율을 곱하면 적중률에 비례한 가중치.
    """
    acc = _load_pattern_accuracy()
    st = acc.get(ptype)
    if not st or st.get('total', 0) == 0:
        return 1.0  # 데이터 없으면 하드코딩 유지
    hits  = st['correct']
    total = st['total']
    laplace = (hits + 1) / (total + 2)  # 라플라스 스무딩
    # 블렌딩 (fires가 적을수록 하드코딩 비중 ↑)
    alpha = min(1.0, total / _ADAPTIVE_MIN_FIRES)
    blended = alpha * laplace + (1 - alpha) * 0.5
    # 50% 기준으로 배율 계산 (50%면 1.0, 60%면 1.2, 40%면 0.8)
    return max(0.1, blended / 0.5)

def _info_factor(desc):
    """패턴 설명에서 random_rate를 조회해 정보량 배율 반환 (1 - rate).
    P5: 추가로 누적 적중률 기반 적응형 배율을 곱함."""
    ptype = _extract_pattern_type(desc)
    rate = _RANDOM_RATE.get(ptype, 0.0)  # 미측정 패턴은 페널티 없음
    random_factor = max(0.05, 1.0 - rate)
    adaptive = _adaptive_factor(ptype, None)  # P5
    return random_factor * adaptive

def collect_pattern_votes(seq, full_history=None):
    """전체 + 모든 접미사 분할에서 패턴 탐색 → 투표 리스트 반환
    Returns list of (prediction, weight, description)
    길이 비율(length_factor)로 가중: 긴 매칭일수록 신뢰도 높음
    P2 적용: information_factor (1 - random_baseline) 추가 페널티
    """
    votes = []
    n = len(seq)

    def add(p, base_w, d, sub_len):
        if p is not None:
            lf = 0.5 + 0.5 * (sub_len / n)   # 길이 가중 0.5~1.0
            info = _info_factor(d)            # P2: 무작위 발화율 페널티
            votes.append((p, base_w * lf * info, d))

    for start in range(n - 1, -1, -1):
        sub = list(seq[start:])
        m = len(sub)
        if m < 3:
            continue

        # 전체 동일값
        if len(set(sub)) == 1:
            add(1 - sub[0], 0.70, f'연속{sub[0]}', m)

        # 교차(1010)
        if check_alternating(sub):
            add(1 - sub[-1], 0.75, f'교차', m)

        # 반복블록
        rb = check_repeat_block(sub)
        if rb:
            bl, chunk = rb
            add(chunk[m % bl], 0.80, f'반복[{"".join(str(x) for x in chunk)}]', m)

        # 블록분할
        bs = check_block_split(sub)
        if bs:
            sp, fv, bv = bs
            add(fv, 0.82, f'블록분할{fv}→{bv}', m)

        # Fold Mirror
        for (sp_start, sp_mid, sp_end, front, back, tail) in check_fold_mirror(sub)[:2]:
            tr, td = tail_recommendation(list(tail))
            if tr is not None:
                add(tr, 0.85, f'Fold+꼬리({td})', m)

        # P4: 런밸런서 비활성화 (백테스트 47.8%, Wilson LB ≈ 41%, 노이즈)
        # rlb_v, rlb_d, rlb_w = check_run_length_balancer(sub)
        # if rlb_v is not None:
        #     add(rlb_v, rlb_w, rlb_d, m)

        # 런분할
        rv, rd, rw = check_run_mirror_pattern(sub)
        if rv is not None:
            add(rv, rw, f'런분할', m)

        # 꼬리 분할 미러
        tv, td, tw = check_tail_split_mirror(sub)
        if tv is not None:
            add(tv, tw, td, m)

        # 팰린드롬 확장 (홀수+짝수 중심)
        pv, pd, pw = check_palindrome_build(sub)
        if pv is not None:
            add(pv, pw, pd, m)

        # 꼬리 주기 반복
        tc_v, tc_d, tc_w = check_tail_cyclic(sub)
        if tc_v is not None:
            add(tc_v, tc_w, tc_d, m)

        # 접기 + 팰린드롬 꼬리
        fp_v, fp_d, fp_w = check_fold_palindrome_tail(sub)
        if fp_v is not None:
            add(fp_v, fp_w, fp_d, m)

        # 교차 쌍 패턴 (11|00|11... 또는 00|11...)
        cv, cd, cw = check_alternating_pairs(sub)
        if cv is not None:
            add(cv, cw, cd, m)

        # P4: 롤링모멘텀 비활성화 (백테스트 46.0%, Wilson LB ≈ 43%, 노이즈)
        # roll_v, roll_d, roll_w = check_rolling_momentum(sub)
        # if roll_v is not None:
        #     add(roll_v, roll_w, roll_d, m)

    # 분할 패턴 (full seq)
    for desc, part, rec in segment_patterns(seq):
        if rec is not None:
            add(rec, 0.78, f'분할:{desc}', n)

    # 히스토리 + 교대메타 (full seq)
    if full_history is not None:
        for tail_len in range(min(n, 12), 3, -1):
            hv, hd, hw = check_history_match(seq[-tail_len:], full_history)
            if hv is not None:
                add(hv, hw, f'짝맞춤:{hd}', n)
                break
        sim_v, sim_d, sim_w = check_similarity_match(seq, full_history)
        if sim_v is not None:
            add(sim_v, sim_w, f'유사:{sim_d}', n)

    # P1: 중복 투표 dedup — 같은 (패턴타입, 예측값)은 최대 가중치 1표만 유지
    # 모든 접미사 검사로 동일 신호가 4~5번 발화하던 문제 해결
    grouped = {}
    for pred, weight, desc in votes:
        ptype = _extract_pattern_type(desc)
        key = (ptype, pred)
        if key not in grouped or weight > grouped[key][1]:
            grouped[key] = (pred, weight, desc)
    return list(grouped.values())

# P1: 증거량 최소 기준 (저증거 고비율 케이스 차단)
MIN_VOTES_FOR_DECISION = 4    # 패턴 개수 최소치
MIN_WEIGHT_FOR_DECISION = 2.0 # 가중치 합 최소치

def vote_pat_rec(seq, full_history=None):
    """다수결 패턴 분석 (팀승패 / BM 방향 전용)"""
    if len(seq) < 3:
        return None, '데이터 부족'

    votes = collect_pattern_votes(seq, full_history)
    if not votes:
        return None, '불규칙'

    w1 = sum(w for p, w, _ in votes if p == 1)
    w0 = sum(w for p, w, _ in votes if p == 0)
    n1 = sum(1 for p, _, _ in votes if p == 1)
    n0 = sum(1 for p, _, _ in votes if p == 0)
    total_w = w1 + w0
    total_n = n1 + n0

    if total_w == 0:
        return None, '불규칙'

    # P1: 증거량 게이트
    if total_n < MIN_VOTES_FOR_DECISION:
        return None, f'증거부족(n={total_n}<{MIN_VOTES_FOR_DECISION})'
    if total_w < MIN_WEIGHT_FOR_DECISION:
        return None, f'증거부족(w={total_w:.1f}<{MIN_WEIGHT_FOR_DECISION})'

    ratio = max(w1, w0) / total_w
    if ratio < 0.55:
        return None, f'균형({n1}↑:{n0}↓) → 불규칙'

    pred = 1 if w1 >= w0 else 0
    desc = f'다수결 {"↑1" if pred==1 else "↓0"} {n1 if pred==1 else n0}/{total_n}({ratio:.0%})'
    return pred, desc


def vote_pat_rec_detailed(seq, full_history=None):
    """vote_pat_rec + 개별 패턴 로그 반환 (패턴 학습용)
    Returns: (rec, desc, pattern_log)
    pattern_log: list of {'type': str, 'pred': int, 'weight': float}
    """
    if len(seq) < 3:
        return None, '데이터 부족', []

    votes = collect_pattern_votes(seq, full_history)
    if not votes:
        return None, '불규칙', []

    pattern_log = [
        {'type': _extract_pattern_type(d), 'pred': p, 'weight': round(w, 3)}
        for p, w, d in votes
    ]

    w1 = sum(w for p, w, _ in votes if p == 1)
    w0 = sum(w for p, w, _ in votes if p == 0)
    n1 = sum(1 for p, _, _ in votes if p == 1)
    n0 = sum(1 for p, _, _ in votes if p == 0)
    total_w = w1 + w0
    total_n = n1 + n0

    if total_w == 0:
        return None, '불규칙', pattern_log

    # P1: 증거량 게이트 (vote_pat_rec와 동일 기준)
    if total_n < MIN_VOTES_FOR_DECISION:
        return None, f'증거부족(n={total_n}<{MIN_VOTES_FOR_DECISION})', pattern_log
    if total_w < MIN_WEIGHT_FOR_DECISION:
        return None, f'증거부족(w={total_w:.1f}<{MIN_WEIGHT_FOR_DECISION})', pattern_log

    ratio = max(w1, w0) / total_w
    if ratio < 0.55:
        return None, f'균형({n1}↑:{n0}↓) → 불규칙', pattern_log

    pred = 1 if w1 >= w0 else 0
    desc = f'다수결 {"↑1" if pred==1 else "↓0"} {n1 if pred==1 else n0}/{total_n}({ratio:.0%})'
    return pred, desc, pattern_log

def get_bm_odds_seqs(team, before_date_order, window=WINDOW):
    """북메이커별 해당 팀 배당 변동 방향 시퀀스 반환
    - 경기마다 배당이 이전 경기 대비 내렸으면 1(유리해짐), 올랐으면 0(불리해짐)
    - 첫 경기는 기준점이므로 방향값 없음 → window+1 경기 수집 후 diff
    반환: {bookmaker: {dates, odds, seq, current_odds}}
    """
    mask = (
        ((game_df['home'] == team) | (game_df['away'] == team)) &
        (game_df['date_order'] < before_date_order)
    )
    # window+1 경기 수집 (첫 경기는 기준점용)
    recent_games = game_df[mask].sort_values('date_order').tail(window + 1)
    if len(recent_games) < 2:
        return {}

    match_ids = recent_games['match_id'].tolist()
    dates_map = recent_games.set_index('match_id')['date'].to_dict()

    bm_data = df[df['match_id'].isin(match_ids)][
        ['match_id', 'bookmaker', 'home', 'away', 'home_close', 'away_close']
    ].copy()

    # 북메이커별로 경기순 배당값 수집
    raw = {}  # {bm: [(mid, date, team_odds), ...]}
    mid_order = {mid: i for i, mid in enumerate(match_ids)}
    for _, r in bm_data.iterrows():
        bm  = r['bookmaker']
        mid = r['match_id']
        team_odds = r['home_close'] if r['home'] == team else r['away_close']
        opp_odds  = r['away_close'] if r['home'] == team else r['home_close']
        if bm not in raw:
            raw[bm] = []
        raw[bm].append({
            'mid': mid, 'date': dates_map.get(mid, ''),
            'team_odds': round(float(team_odds), 2),
            'opp_odds':  round(float(opp_odds),  2),
            'order': mid_order.get(mid, 99),
        })

    result = {}
    for bm, entries in raw.items():
        entries.sort(key=lambda x: x['order'])
        if len(entries) < 2:
            continue
        odds_list = [e['team_odds'] for e in entries]
        date_list = [e['date']      for e in entries]
        opp_list  = [e['opp_odds']  for e in entries]
        # 방향 시퀀스: 1=내림(유리), 0=오름(불리), -1=동일(제외)
        seq = []
        for i in range(1, len(odds_list)):
            if odds_list[i] < odds_list[i-1]:
                seq.append(1)   # 배당 하락 = 해당 팀 더 유리
            elif odds_list[i] > odds_list[i-1]:
                seq.append(0)   # 배당 상승 = 해당 팀 불리
            # 동일이면 추가 안 함 (변동 없음)
        result[bm] = {
            'seq':          seq,
            'odds':         odds_list[1:],   # 방향 대응 배당값 (기준점 제외)
            'odds_full':    odds_list,        # 전체 (기준 포함)
            'dates':        date_list[1:],
            'current_odds': odds_list[-1],
            'opp_odds':     opp_list[-1],
        }
    return result

def get_slot_bm_odds_seqs(slot, before_date_order, seq_len=BM_SEQ_LEN):
    """슬롯(N번째 경기) 기준 날짜별 북메이커 배당 변동 시퀀스

    신호 추출 (북메이커별):
      winner_change = home_close-home_open  if 홈승 else away_close-away_open
      loser_change  = 반대편
      · winner_change > loser_change → 1
      · winner_change < loser_change → 0
      · 그 외(동일값 / open없음 / 둘다변동없음 / 북메이커누락) → N

    N 조건:
      1. open 데이터 없음 (해당 경기에 open 미수집)
      2. 홈/원정 둘 다 open==close (양쪽 모두 변동 없음)
      3. winner_change == loser_change (변동 동일)
      4. 해당 경기에 북메이커 데이터 자체 없음
    """
    mask = (game_df['slot'] == slot) & (game_df['date_order'] < before_date_order)
    all_games = game_df[mask].sort_values('date_order')
    if len(all_games) < 1:
        return {}

    match_ids       = all_games['match_id'].tolist()
    dates_map       = all_games.set_index('match_id')['date'].to_dict()
    winner_home_map = all_games.set_index('match_id')['winner_is_home'].to_dict()

    bm_data = df[df['match_id'].isin(match_ids)][
        ['match_id', 'bookmaker',
         'home_open', 'home_close',
         'away_open', 'away_close',
         'winner_direction']
    ].copy()

    # 북메이커별 경기 데이터 인덱싱
    bm_mid_map = {}
    for _, r in bm_data.iterrows():
        bm  = r['bookmaker']
        mid = r['match_id']
        if bm not in bm_mid_map:
            bm_mid_map[bm] = {}
        bm_mid_map[bm][mid] = {
            'h_open':  None if pd.isna(r['home_open'])  else float(r['home_open']),
            'h_close': None if pd.isna(r['home_close']) else float(r['home_close']),
            'a_open':  None if pd.isna(r['away_open'])  else float(r['away_open']),
            'a_close': None if pd.isna(r['away_close']) else float(r['away_close']),
            'w_dir':   None if str(r['winner_direction']) in ('N', 'nan', '') else int(r['winner_direction']),
        }

    # Postp 경기 match_id 집합
    postp_mids = set(all_games[all_games['winner'] == 'Postp']['match_id'].tolist())
    # 무승부 경기 match_id 집합 (winner_is_home=NaN이고 winner가 있는 경우 포함)
    draw_mids  = set(all_games[
        all_games['winner_is_home'].isna() &
        ~all_games['winner'].isna() &
        (all_games['winner'] != 'Postp')
    ]['match_id'].tolist())

    result = {}
    for bm, mid_data in bm_mid_map.items():
        all_seq      = []
        all_date_seq = []

        for mid in match_ids:
            date = dates_map.get(mid, '')
            wih  = winner_home_map.get(mid)
            sig  = 'N'

            if mid not in mid_data:
                if mid in postp_mids:
                    all_seq.append('P')
                elif mid in draw_mids:
                    all_seq.append('N')
                else:
                    all_seq.append('F')
                all_date_seq.append(date)
                continue

            e = mid_data[mid]
            h_open, h_close = e['h_open'], e['h_close']
            a_open, a_close = e['a_open'], e['a_close']

            # Postp: BM 데이터가 있어도 P
            if mid in postp_mids:
                all_seq.append('P')
                all_date_seq.append(date)
                continue

            # 무승부: winner_is_home이 None/NaN → N 유지
            if wih is None or (isinstance(wih, float) and pd.isna(wih)):
                all_seq.append('N')
                all_date_seq.append(date)
                continue

            w_is_home = (wih is True or wih == 1)

            # open 없으면 N
            h_chg = round(h_close - h_open, 4) if (h_open is not None and h_close is not None) else None
            a_chg = round(a_close - a_open, 4) if (a_open is not None and a_close is not None) else None

            # winner_direction 명시된 경우 우선 사용
            w_dir_explicit = e.get('w_dir')
            if w_dir_explicit is not None:
                all_seq.append(w_dir_explicit)
                all_date_seq.append(date)
                continue

            if h_chg is None or a_chg is None:
                # h_chg만 있을 때 역방향 추론
                if h_chg is not None and h_chg != 0:
                    h_dir = 1 if h_chg > 0 else 0
                    w_dir_explicit = h_dir if w_is_home else (1 - h_dir)
                all_seq.append(w_dir_explicit if w_dir_explicit is not None else 'N')
                all_date_seq.append(date)
                continue

            w_chg = h_chg if w_is_home else a_chg
            l_chg = a_chg if w_is_home else h_chg

            if   w_chg > l_chg: sig = 1
            elif w_chg < l_chg: sig = 0
            
            all_seq.append(sig)
            all_date_seq.append(date)

        if not any(x not in ('N', 'F') for x in all_seq):
            continue

        seq      = all_seq[-seq_len:]
        date_seq = all_date_seq[-seq_len:]
        current  = next(
            (mid_data[mid]['h_close'] for mid in reversed(match_ids)
             if mid in mid_data and mid_data[mid]['h_close'] is not None),
            None
        )

        result[bm] = {
            'seq':          seq,
            'full_seq':     all_seq,   # 히스토리 조회용 전체 시퀀스
            'dates':        date_seq,
            'current_odds': current,
        }
    return result

def analyze_slot_bm_seqs(slot, before_date_order):
    """슬롯 기준 북메이커별 배당 변동 패턴 분석"""
    bm_seqs = get_slot_bm_odds_seqs(slot, before_date_order)
    results = []
    for bm, data in sorted(bm_seqs.items()):
        seq       = data['seq']
        full_seq  = data.get('full_seq', [])
        # 최근 값이 N/F이면 예측 불가 (데이터 없음)
        if seq and seq[-1] in ('N', 'F'):
            rec, desc = None, '최근데이터없음(N)'
        elif 'P' in seq:
            # P를 세그먼트 경계로 처리: 마지막 P 이후 구간으로 분석
            recent, p_hist = preprocess_seq_p_boundary(seq)
            if not recent:
                rec, desc = None, '데이터 부족'
            else:
                extra = [x for x in full_seq if x in (0, 1)]
                full_for_pat = (extra + p_hist) if extra else p_hist
                rec, desc = vote_pat_rec(recent, full_history=full_for_pat if len(full_for_pat) > len(recent) else None)
        else:
            seq_clean  = preprocess_seq(seq)
            full_clean = [x for x in full_seq if x in (0, 1)]
            rec, desc = vote_pat_rec(seq_clean, full_history=full_clean if len(full_clean) > len(seq_clean) else None)
        results.append({
            'bm':           bm,
            'seq':          seq,
            'rec':          rec,
            'desc':         desc,
            'dates':        data['dates'],
            'current_odds': data['current_odds'],
        })
    return results

def analyze_bm_seqs(team, before_date_order, window=WINDOW):
    """북메이커별 배당 변동 패턴 분석
    반환: list of {bm, seq, rec, desc, odds_full, current_odds, opp_odds}
    """
    bm_seqs = get_bm_odds_seqs(team, before_date_order, window)
    results = []
    for bm, data in sorted(bm_seqs.items()):
        seq  = data['seq']
        # 최근 값이 N/F이면 예측 불가
        if seq and seq[-1] in ('N', 'F'):
            rec, desc = None, '최근데이터없음(N)'
        elif 'P' in seq:
            recent, p_hist = preprocess_seq_p_boundary(seq)
            if not recent:
                rec, desc = None, '데이터 부족'
            else:
                rec, desc = vote_pat_rec(recent, full_history=p_hist if len(p_hist) > len(recent) else None)
        else:
            rec, desc = vote_pat_rec(seq)
        results.append({
            'bm':          bm,
            'seq':         seq,
            'rec':         rec,
            'desc':        desc,
            'odds_full':   data['odds_full'],
            'odds':        data['odds'],
            'dates':       data['dates'],
            'current_odds': data['current_odds'],
            'opp_odds':    data['opp_odds'],
        })
    return results


# ── ML 모델 학습 ──────────────────────────────────────────
print('ML 모델 학습 중...')
X_list, y_list = [], []
for _, g in game_df.sort_values('date_order').iterrows():
    if g.get('winner') == 'Postp' or pd.isna(g['winner_is_home']):
        continue  # Postp 또는 결과 없는 경기 스킵
    feat = make_feat_team(g['home'], g['away'], g['date_order'])
    if feat.count(-1) > WINDOW * 3:  # 데이터 부족 시 스킵
        continue
    X_list.append(feat)
    y_list.append(int(g['winner_is_home']))

X, y = np.array(X_list), np.array(y_list)
print(f'ML 학습 샘플: {len(X)}개')

if len(X) >= 10:
    preds_loo = []
    for tr, te in LeaveOneOut().split(X):
        m = RandomForestClassifier(n_estimators=200, random_state=42)
        m.fit(X[tr], y[tr])
        preds_loo.append(m.predict(X[te])[0])
    ml_acc = accuracy_score(y, preds_loo)
    print(f'ML 정확도(LOO): {ml_acc:.1%} ({int(ml_acc*len(y))}/{len(y)})')
else:
    ml_acc = 0.5
    print('ML 샘플 부족 → 스킵')

model = RandomForestClassifier(n_estimators=200, random_state=42)
if len(X) >= 2:
    model.fit(X, y)


# ── 다음 경기 탐색 ─────────────────────────────────────────
def parse_odds_date(raw):
    """Oddsportal 날짜 문자열 → datetime (실패시 None)"""
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    s = str(raw).strip()
    if s.startswith('Today'):
        return today
    if s.startswith('Yesterday'):
        return today - timedelta(days=1)
    s = s.split(' - ')[0].strip()  # "14 Mar 2026 - Pre-season" → "14 Mar 2026"
    for fmt in ('%d %b %Y', '%Y-%m-%d', '%d %b'):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == '%d %b':
                dt = dt.replace(year=today.year)
            return dt
        except:
            continue
    return None

def get_latest_odds_date():
    """kbo_odds.csv 전체 날짜 파싱 후 최대값 반환"""
    parsed = [parse_odds_date(d) for d in df['date'].unique()]
    parsed = [d for d in parsed if d is not None]
    return max(parsed) if parsed else None

def find_upcoming_games():
    """kbo_today_odds.json → kbo_games.csv 순서로 다음 경기일 탐색"""
    # 1순위: kbo_today_odds.json에 오늘 날짜 데이터가 있으면 사용
    today_str = datetime.today().strftime('%Y-%m-%d')
    if os.path.exists('kbo_today_odds.json'):
        try:
            with open('kbo_today_odds.json', encoding='utf-8') as f:
                tod = json.load(f)
            today_entries = sorted(
                [v for v in tod.values() if v.get('date') == today_str],
                key=lambda x: x.get('slot', 99)
            )
            if today_entries:
                games = []
                for v in today_entries:
                    games.append({
                        'date': today_str,
                        'home': v['home'],
                        'away': v['away'],
                        'slot': v['slot'],
                        'winner': None,
                        'winner_is_home': None,
                    })
                print(f'kbo_today_odds.json 기반 예측: {today_str} ({len(games)}경기)')
                return games, today_str
        except Exception:
            pass

    # 2순위: kbo_games.csv에서 미래 경기 탐색
    if not os.path.exists(GAMES_PATH):
        return [], None

    gdf = pd.read_csv(GAMES_PATH)
    latest_dt = get_latest_odds_date()
    if latest_dt is None:
        return [], None

    for delta in range(1, 8):
        target = (latest_dt + timedelta(days=delta)).strftime('%Y-%m-%d')
        day_games = gdf[(gdf['date'] == target) & (gdf['winner'].isna())]
        if len(day_games) > 0:
            return day_games.to_dict('records'), target

    return [], None

if globals().get('_BACKTEST_ONLY', False):
    raise SystemExit(0)  # backtest 모드: 함수/모델 로드만 하고 종료

upcoming_games, pred_date = find_upcoming_games()

# fallback: kbo_games.csv에 없으면 odds 마지막 날 경기들로 예측
if not upcoming_games:
    latest_date_order = game_df['date_order'].max()
    last_games = game_df[game_df['date_order'] == latest_date_order]
    upcoming_games = last_games.to_dict('records')
    pred_date = game_df[game_df['date_order'] == latest_date_order]['date'].iloc[0]
    print(f'kbo_games.csv 미탐색 → 마지막 기록 경기 재예측 ({pred_date})')
else:
    print(f'예측 대상 날짜: {pred_date} ({len(upcoming_games)}경기)')


# ── 경기별 예측 ───────────────────────────────────────────
print('\n' + '='*60)
print(f'패턴 분석 및 예측 ({pred_date})')
print('='*60)

max_date_order = game_df['date_order'].max() + 1  # 미래 date_order

predictions = {}

for i, game in enumerate(upcoming_games):
    home = game['home']
    away = game['away']
    slot = game.get('slot', i + 1)

    # 팀별 4개 시퀀스 수집
    h_dir, h_agr, h_fav_win, h_team_win = get_team_triple_seq(home, max_date_order)
    a_dir, a_agr, a_fav_win, a_team_win = get_team_triple_seq(away, max_date_order)

    # 슬롯별 정배승/역배승 시퀀스 (N번째 경기 날짜별 추이)
    slot_fav_seq, slot_fav_dates = get_slot_fav_win_seq(slot, max_date_order)

    # 패턴 분석 (각 팀 × 4 시퀀스)
    h_dir_rec,  h_dir_desc  = pat_rec(h_dir)
    h_agr_rec,  h_agr_desc  = pat_rec(h_agr)
    h_faw_rec,  h_faw_desc, _  = vote_pat_rec_detailed(h_fav_win)
    h_win_rec,  h_win_desc, h_pattern_log  = vote_pat_rec_detailed(h_team_win)

    slot_fav_rec, slot_fav_desc, _ = vote_pat_rec_detailed(slot_fav_seq)

    # 오늘 슬롯의 정배팀(홈/원정)을 실제 배당으로 확인 → team 추천 변환
    # 1순위: 동일 홈/원정 매치업 중 가장 최근 컨센서스 (팀 구성 기반)
    # 1순위: 오늘 실제 개장 배당 (kbo_today_odds.json)
    _todayodds = get_today_odds(slot, home, away, pred_date)
    if _todayodds and _todayodds.get('home_odds') and _todayodds.get('away_odds'):
        home_is_fav_today = _todayodds['home_odds'] < _todayodds['away_odds']
        print(f'  [실시간배당] {home}({_todayodds["home_odds"]}) vs {away}({_todayodds["away_odds"]}) → {"홈정배" if home_is_fav_today else "원정정배"}')
    else:
        # 2순위: 동일 매치업 최근 컨센서스
        _same_matchup = game_df[
            (game_df['home'] == home) &
            (game_df['away'] == away) &
            (game_df['date_order'] < max_date_order) &
            (game_df['bm_count'] > 0)
        ].sort_values('date_order').tail(1)
        if len(_same_matchup) > 0:
            home_is_fav_today = (_same_matchup['consensus'].iloc[0] == 'home')
        else:
            _home_recent = game_df[
                (game_df['home'] == home) &
                (game_df['date_order'] < max_date_order) &
                (game_df['bm_count'] > 0)
            ].sort_values('date_order').tail(1)
            home_is_fav_today = (_home_recent['consensus'].iloc[0] == 'home') if len(_home_recent) > 0 else None
    slot_fav_team_rec = None
    if slot_fav_rec is not None and home_is_fav_today is not None:
        # 정배승(1)+홈이정배 → HOME(1), 정배승(1)+원정이정배 → AWAY(0)
        # 역배승(0)+홈이정배 → AWAY(0), 역배승(0)+원정이정배 → HOME(1)
        slot_fav_team_rec = 1 if (slot_fav_rec == int(home_is_fav_today)) else 0

    a_dir_rec,  a_dir_desc  = pat_rec(a_dir)
    a_agr_rec,  a_agr_desc  = pat_rec(a_agr)
    a_faw_rec,  a_faw_desc, _  = vote_pat_rec_detailed(a_fav_win)
    a_win_rec,  a_win_desc, a_pattern_log  = vote_pat_rec_detailed(a_team_win)

    # 현재 경기 북메이커 통계 (game_df의 가장 최신 행 재사용)
    def bm_summary(team, is_home):
        last = game_df[
            ((game_df['home'] == team) | (game_df['away'] == team))
        ].sort_values('date_order').tail(1)
        if len(last) == 0:
            return ''
        r = last.iloc[0]
        if pd.isna(r.get('home_pct')) or pd.isna(r.get('bm_count')) or int(r.get('bm_count', 0)) == 0:
            return '최근경기 북메이커 데이터 없음'
        pct = r['home_pct'] if is_home else 1 - r['home_pct']
        n   = int(r['bm_count'])
        favoring = round(pct * n)
        return f'최근경기 {favoring}/{n}북메이커({pct:.0%}) 지지'

    def fmt_rec(rec):
        if rec is None: return ' ?'
        return f' {rec}'

    print(f'\n{"="*68}')
    print(f'  {home}  vs  {away}')
    print(f'{"="*68}')
    print(f'  {"항목":<18} {"홈팀 "+home[:14]+" 시퀀스":^24}  {"원정팀 "+away[:12]+" 시퀀스":^24}')
    print(f'  {"-"*66}')

    # 1) 정배여부 (북메이커 다수결: 해당팀 정배=1, 역배=0)
    h_d = seq_str(h_dir); a_d = seq_str(a_dir)
    print(f'  {"정배여부(다수결)":<18} [{h_d}]→{fmt_rec(h_dir_rec):<3}  [{a_d}]→{fmt_rec(a_dir_rec)}')
    print(f'  {"":18} {bm_summary(home, True)}')
    print(f'  {"":18} {bm_summary(away, False)}')

    # 2) 북메이커 일치도 (1=강한쏠림≥70%, 0=분열<70%)
    h_ag = seq_str(h_agr); a_ag = seq_str(a_agr)
    print(f'  {"북메이커 일치도":<18} [{h_ag}]→{fmt_rec(h_agr_rec):<3}  [{a_ag}]→{fmt_rec(a_agr_rec)}')
    print(f'  {"":18} (1=70%↑ 쏠림, 0=의견분열)')

    # 3) 슬롯별 정배승(1)/역배승(0) — 날짜별 N번째 경기 기준 통합
    sf = seq_str(slot_fav_seq)
    date_labels = ' '.join(d.replace('Yesterday, ','').replace('Today','오늘')[-5:] for d in slot_fav_dates[-len(slot_fav_seq):])
    _fav_today_str = ('홈정배' if home_is_fav_today else '원정정배') if home_is_fav_today is not None else '?'
    _fav_team_str  = f'→{"홈" if slot_fav_team_rec==1 else "원정"}' if slot_fav_team_rec is not None else '→?'
    print(f'  {"정배승/역배승":<18} [{sf}]→{fmt_rec(slot_fav_rec):<3}  ({SLOT_FAV_SEQ_LEN}경기, 오늘{_fav_today_str}{_fav_team_str})')
    print(f'  {"":18} {slot_fav_desc}')

    # 4) 팀 승(1) / 패(0)
    h_tw = seq_str(h_team_win); a_tw = seq_str(a_team_win)
    print(f'  {"팀 승패":<18} [{h_tw}]→{fmt_rec(h_win_rec):<3}  [{a_tw}]→{fmt_rec(a_win_rec)}')
    print(f'  {"":18} {h_win_desc}')
    print(f'  {"":18} {a_win_desc}')

    # ── BM 배당변동 방향 신호 (final_rec 이전에 계산) ────────────
    slot_bm_analyses = analyze_slot_bm_seqs(slot, max_date_order)
    s_recs = [e['rec'] for e in slot_bm_analyses if e['rec'] is not None]
    sv1 = sum(s_recs) if s_recs else 0
    sv0 = len(s_recs) - sv1 if s_recs else 0

    # BM 방향 투표: 배당↓팀(마켓정배) 이김(1) vs 배당↑팀(이변) 이김(0)
    bm_dir_vote  = None
    bm_team_rec  = None
    bm_dir_ratio = 0.0
    if sv1 + sv0 > 0:
        bm_dir_ratio = max(sv1, sv0) / (sv1 + sv0)
        if bm_dir_ratio >= 0.6:
            bm_dir_vote = 1 if sv1 > sv0 else 0
        # 팀 매핑: 오늘 실제 open/close 방향 사용 (kbo_today_scrape.py 수집 결과)
        # bm_dir_vote=1(배당↑팀이김=이변):  오늘 배당↑팀 → 그 팀 예측
        # bm_dir_vote=0(배당↓팀이김=정배):  오늘 배당↓팀 → 그 팀 예측
        # today_home_dir=1(홈배당↑): 배당↑팀=HOME → bm_dir_vote=1이면 HOME(1), =0이면 AWAY(0)
        # today_home_dir=0(홈배당↓): 배당↓팀=HOME → bm_dir_vote=0이면 HOME(1), =1이면 AWAY(0)
        # ⇒ bm_team_rec = 1 if (bm_dir_vote == today_home_dir) else 0
        today_home_dir = _todayodds.get('today_home_dir') if _todayodds else None
        today_up_team   = _todayodds.get('today_up_team', '') if _todayodds else ''
        today_down_team = _todayodds.get('today_down_team', '') if _todayodds else ''
        if bm_dir_vote is not None and today_home_dir is not None:
            bm_team_rec = 1 if (bm_dir_vote == today_home_dir) else 0

    # bm_label: 방향 패턴 + 예측 팀명 (today_home_dir 없으면 팀명 미표시)
    if bm_dir_vote is not None:
        _dir_sym   = '↑' if bm_dir_vote == 1 else '↓'
        if bm_team_rec is not None:
            _pred_team = home if bm_team_rec == 1 else away
            _team_str  = f' : {_pred_team}'
        else:
            _team_str  = ' (방향미확인)'
        bm_label   = f'배당{_dir_sym}팀이김 {max(sv1,sv0)}/{sv1+sv0}({bm_dir_ratio:.0%}){_team_str}'
    else:
        bm_label = f'불명확 {sv1}/{sv0}'

    # 패턴 종합 추천 (팀 승패 기준: h_win_rec=1 → 홈팀 승, a_win_rec=1 → 원정팀 승)
    home_rec = h_win_rec
    away_rec = a_win_rec
    home_pa  = analyze_pattern(h_team_win) if len(h_team_win) >= 3 else None
    away_pa  = analyze_pattern(a_team_win) if len(a_team_win) >= 3 else None
    home_score = home_pa['score'] if home_pa else 0.5
    away_score = away_pa['score'] if away_pa else 0.5

    # ── 팀 패턴 분석 (참고용) ─────────────────────────────────
    _pat_rec = None
    _pat_reason = ''
    _pat_conf = 0.0

    if home_rec == 1 and away_rec == 0:
        _pat_rec = 1; _pat_conf = (home_score + away_score) / 2
        _pat_reason = f'홈 승 패턴({home_score:.0%}) + 원정 패 패턴({away_score:.0%})'
    elif home_rec == 0 and away_rec == 1:
        _pat_rec = 0; _pat_conf = (home_score + away_score) / 2
        _pat_reason = f'홈 패 패턴({home_score:.0%}) + 원정 승 패턴({away_score:.0%})'
    elif home_rec == 1 and away_rec is None:
        _pat_rec = 1; _pat_conf = home_score * 0.8
        _pat_reason = f'홈 승 패턴({home_score:.0%}) (원정 불규칙)'
    elif home_rec == 0 and away_rec is None:
        _pat_rec = 0; _pat_conf = home_score * 0.8
        _pat_reason = f'홈 패 패턴({home_score:.0%}) (원정 불규칙)'
    elif home_rec is None and away_rec == 1:
        _pat_rec = 0; _pat_conf = away_score * 0.8
        _pat_reason = f'원정 승 패턴({away_score:.0%}) (홈 불규칙)'
    elif home_rec is None and away_rec == 0:
        _pat_rec = 1; _pat_conf = away_score * 0.8
        _pat_reason = f'원정 패 패턴({away_score:.0%}) (홈 불규칙)'
    elif home_rec == 1 and away_rec == 1:
        _pat_reason = '팀승패 충돌 (둘 다 승 예측)'
    elif home_rec == 0 and away_rec == 0:
        _pat_reason = '팀승패 충돌 (둘 다 패 예측)'

    # ── 슬롯 정배/역배 패턴 반영 (참고용) ────────────────────────
    if slot_fav_team_rec is not None:
        fav_str  = '정배승' if slot_fav_rec == 1 else '역배승'
        fav_who  = '홈정배' if home_is_fav_today else '원정정배'
        fav_label = f'{fav_str} {SLOT_FAV_SEQ_LEN}경기({fav_who})'
        if _pat_rec is None:
            _pat_rec = slot_fav_team_rec; _pat_conf = 0.75
            _pat_reason = f'슬롯정배패턴({fav_label})'
        elif _pat_rec == slot_fav_team_rec:
            _pat_conf = min(0.95, _pat_conf + 0.03)
            _pat_reason += f' + 정배패턴일치({fav_label})'
        else:
            _pat_conf = max(0.50, _pat_conf - 0.03)
            _pat_reason += f' ※정배패턴충돌({fav_label})'

    # ML 먼저 계산 (최종판단 전에 사용)
    feat = make_feat_team(home, away, max_date_order)
    X_pred = np.array(feat).reshape(1, -1)
    try:
        ml_proba = model.predict_proba(X_pred)[0]
    except:
        ml_proba = [0.5, 0.5]
    ml_home = float(ml_proba[1])
    ml_away = float(ml_proba[0])

    # ── 최종판단: BM 패턴예측이 결정 ────────────────────────────
    final_rec = None
    pattern_confidence = 0.0
    pattern_reason = ''

    if bm_team_rec is not None:
        final_rec = bm_team_rec
        pattern_confidence = bm_dir_ratio
        # 팀 패턴이 일치/충돌 여부를 설명에 추가
        if _pat_rec is None:
            agree_str = '(팀패턴 불규칙)'
        elif _pat_rec == bm_team_rec:
            agree_str = f'(팀패턴일치: {_pat_reason})'
        else:
            agree_str = f'(팀패턴충돌: {_pat_reason})'
        pattern_reason = f'{bm_label} {agree_str}'
    elif bm_dir_vote is None:
        # BM 완전 불명확(5/5 동점 등): ML이 55% 이상이면 ML 우선
        if ml_home >= 0.55:
            final_rec = 1
            pattern_confidence = ml_home
            pattern_reason = f'ML우선(BM불명확) 홈={ml_home:.0%} [팀패턴: {_pat_reason or "불규칙"}]'
        elif ml_away >= 0.55:
            final_rec = 0
            pattern_confidence = ml_away
            pattern_reason = f'ML우선(BM불명확) 원정={ml_away:.0%} [팀패턴: {_pat_reason or "불규칙"}]'
        else:
            final_rec = _pat_rec
            pattern_confidence = _pat_conf
            pattern_reason = _pat_reason
    else:
        # BM 방향 있지만 today_home_dir 미확인: 팀 패턴으로 fallback
        final_rec = _pat_rec
        pattern_confidence = _pat_conf
        pattern_reason = _pat_reason

    if final_rec is None:
        if ml_home >= 0.58:
            final_rec = 1
            pattern_confidence = ml_home
        elif ml_away >= 0.58:
            final_rec = 0
            pattern_confidence = ml_away

    print(f'  {"-"*60}')
    print(f'  패턴 판단: {pattern_reason}')
    print(f'  ML 보조:  홈승={ml_proba[1]:.1%} | 원정승={ml_proba[0]:.1%}')

    if final_rec is None:
        print(f'  최종 추천: PASS')
        rec_str = 'PASS'
    else:
        winner_str = f'HOME({home})' if final_rec == 1 else f'AWAY({away})'
        print(f'  최종 추천: {winner_str} 승리 (신뢰도 {pattern_confidence:.1%})')
        rec_str = 'HOME(1)' if final_rec == 1 else 'AWAY(0)'

    # ── 슬롯 기준 북메이커 배당변동 (날짜별 N번째 경기) ────────────
    print(f'\n  ▶ [슬롯{slot}] 날짜별 북메이커 배당변동 (1=배당+오름, 0=배당-내림)')
    print(f'  {"북메이커":<16} {"시퀀스":<{BM_SEQ_LEN+2}} {"예측":^5} {"날짜흐름"}')
    print(f'  {"-"*70}')
    slot_bm_results = {}
    for entry in slot_bm_analyses:
        s   = seq_str(entry['seq'])
        rec = entry['rec']
        rec_sym = f'→{rec}' if rec is not None else '→?'
        dates_short = [d[-5:] if len(d) >= 5 else d for d in entry['dates']]
        date_flow = ' '.join(dates_short)
        print(f'  {entry["bm"]:<16} [{s}]{rec_sym:<4} {date_flow}')
        slot_bm_results[entry['bm']] = {
            'seq': s, 'rec': rec, 'desc': entry['desc'],
            'current_odds': entry.get('current_odds'),
        }
    # 슬롯 북메이커 집계 (sv1/sv0는 위에서 이미 계산됨)
    if sv1 + sv0 > 0:
        print(f'\n  → 슬롯{slot} 집계: 배당↓팀이김(1) {sv1}개 / 배당↑팀이김(0) {sv0}개 (총 {sv1+sv0}개)')

    predictions[f'slot_{slot}'] = {
        'slot':            slot,
        'home':            home,
        'away':            away,
        'pred_date':       pred_date,
        # 홈팀 4 시퀀스
        'home_direction':  seq_str(h_dir),
        'home_bm_agree':   seq_str(h_agr),
        'home_fav_win':    seq_str(h_fav_win),
        'home_team_win':   seq_str(h_team_win),
        'home_dir_rec':    h_dir_rec,
        'home_agr_rec':    h_agr_rec,
        'home_fav_rec':    h_faw_rec,
        'home_win_rec':    h_win_rec,
        # 원정팀 4 시퀀스
        'away_direction':  seq_str(a_dir),
        'away_bm_agree':   seq_str(a_agr),
        'away_fav_win':    seq_str(a_fav_win),
        'away_team_win':   seq_str(a_team_win),
        'away_dir_rec':    a_dir_rec,
        'away_agr_rec':    a_agr_rec,
        'away_fav_rec':    a_faw_rec,
        'away_win_rec':    a_win_rec,
        'slot_fav_win':    seq_str(slot_fav_seq),
        'slot_fav_rec':    slot_fav_rec,
        'slot_fav_desc':   slot_fav_desc,
        'slot_fav_team_rec': slot_fav_team_rec,
        'home_is_fav':     home_is_fav_today,
        'slot_bm':         slot_bm_results,
        'recommendation':  rec_str,
        'confidence':      round(pattern_confidence, 3),
        'pattern_reason':  pattern_reason,
        'home_win_desc':   h_win_desc,
        'away_win_desc':   a_win_desc,
        'bm_label':        bm_label,
        'bm_dir_vote':     bm_dir_vote,
        'bm_team_rec':     bm_team_rec,
        'bm_dir_ratio':    round(float(bm_dir_ratio), 3),
        'ml_home_prob':    round(float(ml_proba[1]), 3),
        'ml_away_prob':    round(float(ml_proba[0]), 3),
        'home_pattern_log': h_pattern_log,
        'away_pattern_log': a_pattern_log,
        'verified':        False,
        'actual':          None,
    }

def _atomic_json(path, data):
    dir_ = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise

# ① 스냅샷 먼저 저장 (검증 기준 — 재실행해도 덮이지 않음)
os.makedirs('snapshots', exist_ok=True)
snap_path = f'snapshots/kbo_predictions_{pred_date}.json'
if not os.path.exists(snap_path):
    _atomic_json(snap_path, predictions)
    print(f'스냅샷 저장: {snap_path}')

# ② 메인 예측 파일 저장 (atomic)
_atomic_json(PRED_PATH, predictions)
print(f'\n예측 저장 완료: {PRED_PATH}')
