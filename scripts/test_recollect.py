"""recollect_range.py 단일 경기 테스트"""
import sys
sys.path.insert(0, '.')

# TARGET_MATCHES를 하나만 테스트하도록 패치
import recollect_range as r
r.TARGET_MATCHES = [r.TARGET_MATCHES[0]]  # 05-02 Slot1만

r.main()
