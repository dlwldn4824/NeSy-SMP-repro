# -*- coding: utf-8 -*-
# ============================================================================
# 그림: 첫 CAM 평가까지 걸린 시간
#
# 형태 = 누적 도달 곡선. 이 데이터의 일은 '시간에 따른 도달률'이고,
# 핵심은 두 곡선(첫 기록 vs 첫 확정)이 벌어지는 간격이다 — stay 의 23.7% 가
# 첫 CAM 이 UTA 라 확정까지 median 13.0h 를 더 기다린다.
#
# 색은 dataviz 스킬 references/palette.md 의 검증된 categorical 슬롯 1·2 를 그대로 쓴다.
# 사용: EDA_DATA=<notes/eda> python eda/27_fig_first_cam.py
# ============================================================================
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "notes/eda")
OUTF = os.environ.get("FIG_OUT", "docs/fig_first_cam.png")

for fp in [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"]:
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

S1, S2 = "#2a78d6", "#eb6834"          # 검증된 슬롯 1(blue) · 2(orange)
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8a83"
SURF = "#fcfcfb"

# ---------------------------------------------------------------- 데이터
b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = DEN.set_index("stay_id")["intime"]
MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v[v.itemid == 228332][["stay_id", "charttime", "value"]].copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[cam.hr >= 0]

f_any = cam.groupby("stay_id")["hr"].min()
f_conf = cam[cam.v != "U"].groupby("stay_id")["hr"].min().reindex(f_any.index)
N = len(f_any)
grid = np.linspace(0, 48, 600)
cdf_any = np.array([(f_any <= g).sum() for g in grid]) / N * 100
cdf_conf = np.array([(f_conf <= g).sum() for g in grid]) / N * 100
med_any, med_conf = float(f_any.median()), float(f_conf.median())
mean_any, mean_conf = float(f_any.mean()), float(f_conf.mean())
q_any = (f_any.quantile(.25), f_any.quantile(.75))
q_conf = (f_conf.quantile(.25), f_conf.quantile(.75))
lag = float((f_conf - f_any).replace(0, np.nan).median())
pct_uta_first = 100 * float((f_conf > f_any).mean())

# ---------------------------------------------------------------- 그림
fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=200)
fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)

ax.grid(axis="y", color="#e6e5e0", lw=0.8, zorder=0)
ax.set_axisbelow(True)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
for sp in ("left", "bottom"):
    ax.spines[sp].set_color("#d8d7d1"); ax.spines[sp].set_linewidth(0.8)

ax.plot(grid, cdf_any, color=S1, lw=2, zorder=3, solid_capstyle="round")
ax.plot(grid, cdf_conf, color=S2, lw=2, zorder=3, solid_capstyle="round")
ax.fill_between(grid, cdf_conf, cdf_any, color=S2, alpha=0.10, lw=0, zorder=1)

# median 표시 — 두 값이 x 축에서 1.6h 밖에 안 떨어져 있어 각각 라벨을 달면 겹친다.
# 점만 찍고 설명은 한 덩어리로 오른쪽에 뺀다.
ax.axhline(50, color=MUTED, lw=0.8, ls=(0, (4, 4)), zorder=2)
for m, c in [(med_any, S1), (med_conf, S2)]:
    ax.plot([m], [50], "o", ms=9, mfc=c, mec=SURF, mew=2, zorder=5)
ax.annotate("절반이 첫 평가를 받는 시점", (6.0, 50), textcoords="offset points",
            xytext=(0, 9), fontsize=10, color=MUTED)
ax.annotate(f"{med_any:.1f}h", (6.0, 50), textcoords="offset points", xytext=(0, -18),
            fontsize=11, color=S1, fontweight="bold")
ax.annotate(f" · {med_conf:.1f}h", (6.0, 50), textcoords="offset points", xytext=(26, -18),
            fontsize=11, color=S2, fontweight="bold")

# 직접 라벨 (범례와 함께 — 계열 2개)
ax.annotate("첫 CAM 기록 (UTA 포함)", (48, cdf_any[-1]), textcoords="offset points",
            xytext=(-6, 8), ha="right", fontsize=11, color=S1, fontweight="bold")
ax.annotate("첫 확정 CAM (P/N)", (48, cdf_conf[-1]), textcoords="offset points",
            xytext=(-6, -18), ha="right", fontsize=11, color=S2, fontweight="bold")

# 간격 주석
gx = 12.0
ya = np.interp(gx, grid, cdf_any); yc = np.interp(gx, grid, cdf_conf)
ax.annotate("", xy=(gx, ya), xytext=(gx, yc),
            arrowprops=dict(arrowstyle="<->", color=INK2, lw=1.2))
ax.annotate(f"이 간격 = 첫 CAM 이 UTA 인 stay\n{pct_uta_first:.1f}% · 확정까지 median +{lag:.1f}h",
            (gx, (ya + yc) / 2), textcoords="offset points", xytext=(12, -4),
            fontsize=10, color=INK2, va="center")

ax.set_xlim(0, 48); ax.set_ylim(0, 100)
ax.set_xticks([0, 6, 12, 24, 36, 48])
ax.set_xticklabels(["0", "6h", "12h", "24h", "36h", "48h"], fontsize=10, color=INK2)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_yticklabels(["0", "25", "50", "75", "100%"], fontsize=10, color=INK2)
ax.set_xlabel("ICU 입실 후 경과 시간", fontsize=10.5, color=INK2, labelpad=8)
ax.set_ylabel("첫 평가를 받은 stay 누적 비율", fontsize=10.5, color=INK2, labelpad=8)

ax.set_title("첫 CAM 평가까지 걸린 시간", fontsize=15, color=INK,
             fontweight="bold", loc="left", pad=26)
ax.annotate(f"성인 · ICU LOS ≥ 24h · CAM 보유 {N:,} stay (전체 코호트 {len(DEN):,} 중 {100*N/len(DEN):.1f}%)",
            xy=(0, 1.045), xycoords="axes fraction", fontsize=10, color=MUTED)

foot = (f"첫 기록  평균 {mean_any:.1f}h · median {med_any:.1f}h (IQR {q_any[0]:.1f}–{q_any[1]:.1f})     "
        f"첫 확정  평균 {mean_conf:.1f}h · median {med_conf:.1f}h (IQR {q_conf[0]:.1f}–{q_conf[1]:.1f})\n"
        f"평균이 median 의 2배 이상인 것은 늦은 첫 평가의 오른쪽 꼬리 때문 — 보고에는 median (IQR) 을 쓴다.")
fig.text(0.008, -0.055, foot, fontsize=9.5, color=MUTED, va="top")

os.makedirs(os.path.dirname(OUTF) or ".", exist_ok=True)
fig.savefig(OUTF, bbox_inches="tight", facecolor=SURF)
print(f"저장 -> {OUTF}")
print(f"  첫 기록 median {med_any:.1f}h / 평균 {mean_any:.1f}h · "
      f"첫 확정 median {med_conf:.1f}h / 평균 {mean_conf:.1f}h")
print(f"  첫 CAM 이 UTA 인 stay {pct_uta_first:.1f}% · 확정까지 median +{lag:.1f}h")
