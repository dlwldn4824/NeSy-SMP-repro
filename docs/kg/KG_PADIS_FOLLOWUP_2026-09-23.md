# PADIS 후속 검토 — 근거 유형·공리 강도·실행 조건

작성 2026-09-23 · 선행 문서: `docs/kg/KG_RULE_REVIEW_PADIS.md`(검수표) · `docs/kg/KG_RULE_REVIEW_PADIS.csv` · `padis/docs/PADIS_섬망_지식그래프_정리.md`
대상 코드: `eda/23_stage34_bilstm_cbm.py`(AXIOMS 13개 · GRADE_W) · `eda/28_padis_planned.py`
원문 자료: `padis/outputs/padis_rules_raw.json`(2018 PADIS 에서 '섬망' 포함 문장 86개, p.9~31) · `padis/outputs/_gold_sentences.txt`

> **한계 먼저.** 이번에도 PADIS 2018 전문 PDF 는 확보하지 못했다(Downloads·Documents·학연생 폴더에 없음). 아래 원문 검증은 **추출 문장 86개 범위 안에서만** 확정이며, p.18 Ungraded Statement 의 잘린 부분(치매·선행 혼수·응급수술/외상·APACHE)은 여전히 미검증이다. 2025 Focused Update 원문도 없다.

---

## 1. "섬망 → 사망"은 2018 원문이 직접 뒷받침하지 않는다

**검증 방법.** 추출 문장 86개 전체에서 `mortality | death | died | survival` 를 검색해 12개 문장을 찾고, 각 문장이 **섬망(원인) → 사망(결과)** 을 진술하는지 확인했다.

| 문장 | 페이지 | 실제로 말하는 것 | 섬망→사망 지지 |
|---|---|---|:-:|
| D-017 | 14 | **진정 강도**(음의 RASS 합/평가 수)가 사망·섬망·발관 지연 위험 증가를 독립적으로 예측 (가이드라인이 채택하지 않은 코호트) | ❌ (주어가 진정 강도) |
| D-043 | 20 | **섬망 모니터링 순응도**가 높으면 원내 사망률이 낮았다는 관찰연구 | ❌ (주어가 평가 시행) |
| D-050 | 21 | 빠르게 가역적인 진정 관련 섬망 환자와 비섬망 환자의 **1년 사망률이 유사**했다 | ❌ **반대 방향 증거** |
| D-055 | 22 | 예방적 할로페리돌이 섬망 예방·90일 생존에 영향 없음 | ❌ (중재 효과) |
| D-020 · D-053 · D-061 · D-066 · D-086 | 15·21·22·22·31 | 사망률이 **평가 대상 결과(outcome)** 목록에 포함된다는 서술 | ❌ |
| D-026 · D-042 · D-076 | 17·20·24 | 연구 필요성 · 평가 근거 · ABCDEF 번들 순응도와 사망률 감소 | ❌ |

**결론.** 추출 범위 안에 **"섬망이 사망 위험을 높인다"고 진술한 문장은 없다.** draft json 의 R-19 가 인용한 영문장(`Delirium is associated with increased mortality…`)은 원문 추출본 어디에도 없다(검수표 §5 와 동일 결론, 이번에 전수 검색으로 확인).

**권고.**

1. R-19(`Delirium increasesRiskOf Death`)를 **가이드라인 근거 규칙에서 제외**한다. 남긴다면 등급을 `external`(가이드라인 밖 문헌) 로 표기하고 출처를 PADIS 가 아닌 원 논문으로 바꾼다.
2. R-13(`SedationIntensity increasesRiskOf Death`)은 근거가 D-017 **한 건의 미채택 코호트**다. 등급 `cohort` 유지, 공리 가중치는 최저 구간에 둔다.
3. 사망을 결과로 쓰는 규칙은 현재 모델(결과 = 섬망 발생)에서 **쓰이지 않는다**. 논문에 인용할 때 "PADIS 는 섬망의 예후로서 사망을 규정하지 않는다"는 점을 명시한다.

---

## 2. 위험인자 진술과 인과 표현의 구분

2018 PADIS 의 섬망 위험인자 절은 **Ungraded, nonactionable statement** 이고, 문장은 "associated with"(연관)로 쓰여 있다. 반면 KG 의 관계명은 `increasesRiskOf` 하나이고, 코드의 공리는 이를 **함축**(A → 섬망)으로 학습시킨다. 즉 표현 층위가 세 개(연관 진술 · 중재 효과 · 논리 함축)인데 하나로 뭉뚱그려져 있다.

**제안: 규칙마다 `claimType` 필드를 둔다.**

| claimType | 정의 | 원문 표지 | 해당 규칙(예) |
|---|---|---|---|
| `association` | 관찰된 연관. 인과·개입 효과 아님 | "associated with", Ungraded Statement, 위험인자 절 | R-01 벤조 · R-02 수혈 · R-03 고령 · R-04 치매 · R-05 선행 혼수 · R-07 외상 · R-09 고혈압 · R-10 신경계 입실 · R-11 향정신성약물 |
| `intervention` | 중재가 결과를 바꾼다는 GRADE 권고 | "we suggest/recommend", 확실성 등급 | R-16 덱스메데토미딘 · R-17 조기 거동 · R-18 멜라토닌 |
| `no-effect` | 효과 없음을 진술 (반대 방향 규칙을 기각) | "not associated with", strong | D-016 얕은 진정 · D-032 기계환기·아편유사제 |
| `cohort` | 가이드라인이 채택하지 않은 코호트/데이터 파생 | Rationale 속 개별 연구 | R-12 깊은 진정 · R-13 진정 강도 · X-01 |
| `outcome-list` | 결과 변수 나열일 뿐 규칙이 아님 | "outcomes deemed critical…" | D-020 · D-053 · D-061 · D-066 |

**적용 원칙**

- `association` 규칙은 **인과로 읽지 않는다**. 논문·KG 주석에 "risk marker, not established cause" 를 명시한다.
- `association` 과 `intervention` 은 **같은 가중치 척도를 공유하지 않는다**(§3).
- `outcome-list` 는 규칙화하지 않는다 — 현재 draft 의 잡음 원인이다.
- `no-effect(strong)` 는 같은 개념의 서술형 `increasesRiskOf` 를 기각한다(검수표 §4.4 정책 4와 동일).

---

## 3. 공리 강도 조정안

**현재** (`eda/23_stage34_bilstm_cbm.py:417`)

```python
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3,
           "derived": 0.5, "inconclusive": 0.2}
```

문제: `strong`(연관 근거의 강도) 과 `moderate`(중재 효과의 확실성) 가 한 자에 섞여 있고, 원문이 "연관"만 말한 규칙이 함축 공리에서 1.0 을 받는다.

**제안: 두 축으로 나눈 뒤 곱한다.**

```python
CLAIM_W = {"association": 0.6, "intervention": 1.0, "cohort": 0.4, "external": 0.3}
CERT_W  = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "inconclusive": 0.0}
w = CLAIM_W[claim] * CERT_W[cert]          # 0 이면 공리에서 제외
```

| 공리 (코드 이름) | 현재 등급 · 가중치 | 제안 claim · cert | 제안 가중치 | 근거 |
|---|---|---|---:|---|
| Benzo→Delirium | strong 1.0 | association · strong | 0.60 | D-030/D-031 연관 진술 |
| OlderAge→Delirium | strong 1.0 | association · strong | 0.60 | 같은 Ungraded 목록 |
| BloodTransfusion→Delirium | strong 1.0 | association · strong | 0.60 | 같은 목록 |
| Dementia→Delirium | strong 1.0 | association · strong(미검증) | 0.60 | p.18 잘린 부분 — PDF 확인 전까지 표기 유지 |
| **Trauma→Delirium** | strong 1.0 | association · **moderate** | **0.36** | 확인 가능한 원문(D-033)은 moderate. strong 은 '입실 전 응급수술/외상' 한정자가 있는 미검증 문장 |
| Hypertension→Delirium | moderate 0.6 | association · moderate | 0.36 | D-033 |
| DeepSedation→Delirium | low 0.3 | cohort · low | 0.12 | 얕은 진정 권고의 대우는 불인정, D-017 코호트로 대체 |
| SedationIntensity→Delirium | cohort 0.3 | cohort · moderate | 0.24 | D-017(용량-반응, 미채택 코호트) |
| **SeverePain→Delirium** | inconclusive 0.2 | association · **inconclusive** | **0.00 (제외)** | 인용 문장이 아편유사제 안전성 서술. 코호트도 반대(RR 0.37) |
| Dexmed→¬Delirium | moderate 0.6 | intervention · moderate | 0.60 | 단 **모집단·비교군 한정자 필요**(기계환기 진정, 벤조 대비) |
| EarlyMobility→¬Delirium | low 0.3 | intervention · low | 0.30 | 결과가 '섬망 기간'인 권고를 '발생'에 쓰는 문제 잔존 |
| DeepSedation→CurrentUTA | derived 0.5 | cohort · moderate | 0.24 | 측정 가능성 규칙(가이드라인 규칙 아님) |
| Delirium→Death (R-19) | — | external · — | **미사용** | §1 |

**효과.** 양의 방향 공리 총 가중치가 줄고(9:3 → 실질 8:3, SeverePain 제거), 중재 근거가 있는 음의 방향 두 건의 상대 비중이 올라간다. 검수표 §4.5 가 지적한 collapse 위험 완화에도 같은 방향이다.

**주의.** 이 조정은 **성능을 올리기 위한 튜닝이 아니라 근거 층위를 반영한 것**이다. 기존 결과와 비교할 때는 가중치 변경 전/후를 함께 보고한다.

---

## 4. 시간 창 · 집계 · 결측 처리 명세

`eda/23_stage34_bilstm_cbm.py` 의 실제 구현을 읽어 명시한다. 지금까지 문서에 적혀 있지 않아 규칙 해석이 코드에만 존재했다.

**공통 축**

| 항목 | 값 | 코드 |
|---|---|---|
| 앵커 | CAM-ICU 기록 1건 (ICU 입실 후 0~240h) | `CAM_ITEM=228332`, `HR_CAP=240` |
| 관찰 창 | 앵커 이전 **24시간**, 1시간 간격 24개 구간 | `NBIN=24` |
| 예측 지평 | 앵커 이후 **24시간** 안의 CAM-ICU 양성 | `W_AHEAD=24.0` |
| 분할 | 환자 단위 test 30% (seed 42) · train 중 15%p val | `SEED=42` |
| 대상 | 성인(≥18) · ICU 재원 ≥ 1일 | `DEN` |

**공리별 실행 조건**

| 개념 | 원 자료 | 집계 | 임계값 | 결측 처리 (현재) | 지적 |
|---|---|---|---|---|---|
| RASSmin | RASS(228096) 기록 구간 | 24구간 **최솟값** | ≤ −4 | 기록 없으면 0 대입 + 마스크 | 0 은 "각성·평온"과 같은 값 — 마스크를 쓰지 않는 경로에서는 '깊은 진정 아님'으로 읽힌다 |
| RASSnegmean | 같음 | 음수 RASS 합 / 기록 수 | ≤ −2 | 기록 없으면 0 | 위와 같음 |
| BenzoFrac / DexmedFrac | 투여 플래그 | 24구간 **평균**(투여 구간 비율) | > 0 | 결측 = 0 = 미투여 | 투여 기록 누락과 미투여가 구분되지 않음 |
| GCStotal | GCS 3성분 | 성분별 **최솟값** 합 | ≤ 8 | 성분 중 하나라도 없으면 마스크 off, 값 0 | **0 ≤ 8 이라 마스크를 잃으면 전원 참** — NeSy-SMP 에서 발견한 것과 같은 유형 |
| MobJHHLM | JHHLM | 24구간 **최댓값** | ≥ 4 | 없으면 0 + 마스크 | 0 은 '완전 부동'과 같은 값 |
| PainNRSmax | NRS | 24구간 **최댓값** | ≥ 4 | 없으면 0 + 마스크 | 0 = 통증 없음과 동일 |
| Age | 입실 시 나이 | — | ≥ 65 | 없음 | — |
| Dementia · Trauma · Hypertension | 진단(입원 단위) | 있음/없음 | > 0 | 없으면 0 | **시점 정보 없음** — 입실 전 병력과 입원 중 진단이 섞인다 |
| BloodTransfusion | 수혈 | **앵커 이전 24h** | > 0 | 없으면 0 | 창이 다른 개념과 일치함 |

**표기 규칙 제안**

1. 모든 규칙에 `window`(예: `anchor-24h`), `agg`(min/max/mean/frac/any), `threshold`, `missing`(`mask` / `zero` / `unknown`) 네 필드를 **필수**로 둔다. 비어 있으면 컴파일 실패로 처리한다.
2. 결측 기본값은 `mask`(공리 평가에서 제외)로 하고, `zero` 대입은 "미투여 = 0" 이 임상적으로 성립하는 개념(약물 노출)에만 허용한다.
3. 병력 개념(치매·외상·고혈압)은 `window: pre-icu` 로 표기하고, 구현이 입원 단위라면 `window: hadm(approx)` 로 **근사임을 명시**한다.
4. 임계값은 원문에 있으면 그 값을, 없으면 `derived` 로 표시하고 정한 사람과 근거를 남긴다(예: JHHLM ≥ 4).

---

## 5. 규칙별 원문 근거 + 실행 조건 기록

`docs/kg/KG_PADIS_RULE_EXEC_SPEC.csv` 에 규칙 단위로 다음을 기록했다 — 검수표(`KG_RULE_REVIEW_PADIS.csv`)가 **근거·판정**을 담는다면, 이 표는 **실행 조건**을 담는다.

열: `규칙ID · 주어 · 관계 · 목적어 · claimType · 원문문장ID · 페이지 · 원문요약 · 원문등급 · 현재가중치 · 제안가중치 · MIMIC변수 · 시간창 · 집계 · 임계값 · 결측처리 · 모델사용 · 비고`

---

## 6. 남은 확인 항목 (PDF 확보 시)

1. p.18 Ungraded Statement 의 'greater' 이후 목록 → R-04 치매 · R-05 선행 혼수 · R-06 응급수술 · R-07 외상 한정자 · R-08 APACHE.
2. p.18 raw D-027/D-028 의 주어가 신체억제대인지 (현재는 추정).
3. 2025 Focused Update → R-16(프로포폴 대비) · R-17(기간 단축) · R-18(멜라토닌).
4. 위 1~3 이 확인되면 §3 표의 `미검증` 표기를 갱신한다.
