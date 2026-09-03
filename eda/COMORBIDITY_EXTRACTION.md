# 동반질환 23개 추출 결과 (원 논문 재현)

원 논문 `extract_comorbidities.py` 의 medspaCy 파이프라인을 그대로 사용.
로컬 Windows 에서 spaCy 컴파일 확장이 애플리케이션 제어 정책에 차단되어 Colab 에서 실행.

---

## 1. 실행 결과

| | |
|---|---:|
| 입력 노트 | 52,488건 (ICU 환자 discharge summary) |
| 소요 시간 | **9시간 51분** |
| 추출 엔티티 | 49,137개 |
| 엔티티가 1개 이상 나온 hadm | **28,744** |
| 추출된 고유 동반질환 | **23종** ✅ |

목록에 있던 26개 TargetRule 이 정규화(`COPD`/`Chronic Obstructive…`→copd, `CAD`/`Coronary Artery Disease`→cad)를 거쳐 23종으로 수렴했다. **목록 자체는 정상 동작했다.**

---

## 2. 유병률

| 동반질환 | % | | 동반질환 | % |
|---|---:|---|---|---:|
| pneumonia | 25.6 | | trauma | 3.7 |
| cad | 24.9 | | diabetes mellitus | 3.3 |
| **hypertension** | **24.6** | | lymphoma | 2.9 |
| cancer | 20.0 | | metastatic disease | 2.7 |
| copd | 12.7 | | kidney disease | 2.4 |
| **diabetes** | **10.7** | | hiv | 2.0 |
| atrial fibrillation | 9.8 | | leukemia | 0.9 |
| cirrhosis | 8.6 | | acute kidney injury | 0.5 |
| heart failure | 7.8 | | peptic ulcer disease | 0.4 |
| dementia | 5.2 | | kidney failure | 0.4 |
| | | | cerebrovascular accident | 0.4 |
| | | | aids | 0.3 |
| | | | metastatic cancer | 0.2 |

hadm 당 평균 **1.70개**

---

## 3. ⚠️ 문제 — 유병률이 임상 상식보다 낮다

| 항목 | 추출 결과 | ICU 환자 통상 범위 |
|---|---:|---|
| **hypertension** | **24.6%** | **50~60%** |
| **diabetes** (+ diabetes mellitus) | **14.0%** | **30~40%** |
| heart failure | 7.8% | 20~30% |
| cerebrovascular accident | 0.4% | 5~10% |
| acute kidney injury | 0.5% | 20~50% |

중환자실 퇴원 요약서에서 고혈압이 4명 중 1명만 언급된다는 것은 성립하기 어렵다.

**더 결정적인 지표:** 노트 52,488건 중 엔티티가 나온 것은 28,744건뿐이다.
→ **45.2%(23,744건)의 노트에서 동반질환이 하나도 추출되지 않았다.**

ICU 퇴원 요약서에는 `Past Medical History` 섹션이 거의 항상 있으므로, 절반 가까이가 완전히 비는 것은 정상이 아니다.

---

## 4. 원인 추정 — `context_graph.edges`

원 논문 코드의 추출 부분은 다음과 같다.

```python
for target, modifier in doc._.context_graph.edges:
    if modifier.rule.category != "NEGATED_EXISTENCE" and modifier.rule.category != "FAMILY":
        entities.append(target.text)
```

`context_graph.edges` 는 **modifier(수식어)가 연결된 엔티티만** 담는다. medspaCy 의 ConText 알고리즘이 부정어·가족력·과거력 등의 단서를 찾아 엔티티에 연결한 결과다.

따라서 **아무 수식어도 붙지 않은 평범한 언급은 edges 에 들어오지 않는다.**

```text
"Past Medical History: hypertension, diabetes, CAD"
  → 부정어도 가족력 표현도 없음
  → modifier 없음 → edges 에 없음 → 추출 안 됨
```

즉 현재 결과는 **"수식어가 붙은 엔티티 중 부정·가족력이 아닌 것"** 이고,
의도했던 **"부정·가족력이 아닌 모든 엔티티"** 가 아니다.

이것이 사실이면 45.2%의 빈 노트와 낮은 유병률이 동시에 설명된다.

---

## 5. 확인 방법

`doc.ents` 기준으로 바꾸어 같은 노트에 대해 두 결과를 비교한다. **200건이면 몇 분이면 판정된다. 10시간짜리를 다시 돌릴 필요는 없다.**

```python
# 현재 방식
ents_edges = {tg.text.lower() for tg, mod in doc._.context_graph.edges
              if mod.rule.category not in ('NEGATED_EXISTENCE','FAMILY')}

# 대안: 모든 엔티티에서 부정/가족력만 제외
ents_all = {e.text.lower() for e in doc.ents
            if not (e._.is_negated or e._.is_family)}
```

`ents_all` 이 크게 많으면 원인이 확정된다.

---

## 6. 정리할 항목 두 가지

### 중복 개념

23종 안에 사실상 같은 것이 나뉘어 있다. 원 논문 목록을 그대로 쓴 결과다.

```
diabetes            10.7%  +  diabetes mellitus     3.3%
metastatic disease   2.7%  +  metastatic cancer     0.2%
kidney disease       2.4%  +  kidney failure        0.4%
cancer              20.0%  ⊃  leukemia / lymphoma / metastatic *
```

모델 입력으로 쓸 때 병합할지 유지할지 정해야 한다. **원 논문과 동일하게 두는 것이 재현 목적에는 맞다.**

### 시점 문제

`acute kidney injury`, `pneumonia`, `trauma` 는 **기저질환이 아니라 이번 입원 중 발생한 사건**일 수 있다. discharge note 는 퇴원 시점 작성이므로, 이 세 항목을 예측 입력으로 쓰면 미래 정보가 섞인다.

pneumonia 가 25.6%로 hypertension 과 맞먹는 것도 이 때문으로 보인다 — 기저질환이라기보다 이번 입원의 진단명일 가능성이 높다.

원 논문은 이를 구분하지 않았다. 재현에서는 동일하게 두되 **limitation 으로 명시**한다.

---

## 7. 결측이 무작위가 아니다

노트 자체가 없는 환자가 코호트의 27.2%이고, **그 환자들이 더 위중하다.**

| | 노트 있음 | 노트 없음 |
|---|---:|---:|
| 섬망률 | 21.1% | **26.1%** |
| 사망률 | 6.7% | **9.1%** |

동반질환 결측을 0으로 채우면 **위중한 환자가 체계적으로 "지병 없음"으로 처리된다.**
원 논문이 23개를 전부 0으로 둔 것과 같은 방향의 편향이므로, 결과에 반드시 명시한다.

---

## 8. 다음

```
1. doc.ents 방식과 200건 비교          ← 몇 분. 유병률 문제의 원인 확정
2. (원인 확정 시) 추출 방식 수정 후 재실행
3. wide 를 lead time 별 학습 CSV 에 병합   NeSy-SMP/data/merge_comorbidities.py
4. 23개를 0으로 둔 기존 결과와 재학습 결과 비교
   -> NeSy-SMP 우위 미재현의 원인인지 판정
```

**4번이 이 작업의 목적이다.** 현재 epoch 50/20 재현에서 NeSy-SMP 의 우위가 나타나지 않는데, 동반질환 23개가 전부 0인 것이 원인 후보다.

---

산출물: `comorbidities.csv` (long, 49,137행) · `comorbidities_wide.csv` (28,744 × 25)
실행 노트북: `colab/extract_comorbidities.ipynb`
