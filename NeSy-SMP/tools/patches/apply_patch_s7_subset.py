"""[PATCH S7] 학습 데이터 비율을 환경변수로 줄인다 — "데이터가 적을 때 지식이 돕는가" (실험 D6).

NeSy 의 대표적인 주장은 "라벨·데이터가 적을 때 지식이 보완한다" 다. 전체 데이터에서 공리 효과가
fold 변동 수준이라도, 데이터가 적을 때는 벌어질 수 있다. 그래서 **학습 데이터만** 비율로 줄이고
검증·테스트는 그대로 둔 채 LTN(지식 없음) 과 NeSy(지식 있음) 를 비교한다.

바꾸는 곳은 한 군데다 — fold 안에서 train/val 을 나눈 **직후**에 학습셋을 층화 추출로 줄인다.
RF·XGBoost 입력도 이 뒤에서 만들어지므로 **다섯 모델이 모두 같은 부분집합**을 본다.

    NESY_SUBSET=0.1 python stratified_main.py     # 학습셋 10%

사용: python apply_patch_s7_subset.py <대상 stratified_main.py>
"""
from __future__ import annotations

import sys
from pathlib import Path

ANCHOR = ("    X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, "
          "test_size=0.20, stratify=y_train, random_state=seed)")

ADD = '''
    # [PATCH S7] 학습셋만 비율로 줄인다 (검증·테스트는 그대로). 1 이면 원본과 동일.
    _frac = float(os.environ.get("NESY_SUBSET", "1"))
    if _frac < 1.0:
        X_train, _X_drop, y_train, _y_drop = train_test_split(
            X_train, y_train, train_size=_frac, stratify=y_train, random_state=seed)
        print(f"[S7] 학습 데이터 {100 * _frac:.1f}% 사용 -> {len(X_train)} 명 "
              f"(사망 {100 * (sum(y_train) / max(len(y_train), 1)):.1f}%)", flush=True)
'''


def main(path: str) -> None:
    p = Path(path)
    body = p.read_text(encoding="utf-8")
    if "[PATCH S7]" in body:
        raise SystemExit("이미 S7 이 적용돼 있다")
    n = body.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"앵커가 {n}개 — 패치 중단")
    p.write_text(body.replace(ANCHOR, ANCHOR + ADD), encoding="utf-8")
    print(f"S7 적용 완료 -> {p}  (NESY_SUBSET 으로 학습셋 비율 지정)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
