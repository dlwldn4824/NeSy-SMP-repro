# ===== 파일 찾기 진단 셀 — Colab 새 셀에 통째로 붙여넣고 실행 =====
import os, glob

print("[1] 드라이브가 마운트됐나")
print("   /content/drive 존재:", os.path.exists('/content/drive'))
print("   /content/drive/MyDrive 존재:", os.path.exists('/content/drive/MyDrive'))

print("\n[2] 내 드라이브 최상단에 뭐가 있나 (앞 40개)")
try:
    for f in sorted(os.listdir('/content/drive/MyDrive'))[:40]:
        p = f'/content/drive/MyDrive/{f}'
        sz = f"{os.path.getsize(p)/1048576:8.1f} MB" if os.path.isfile(p) else "     <폴더>"
        print(f"   {sz}  {f}")
except Exception as e:
    print("   못 읽음:", e)

print("\n[3] 드라이브 전체에서 이름으로 검색 (하위 폴더 포함)")
hits = []
for pat in ['discharge*', 'patients*', '*.csv.gz']:
    hits += glob.glob(f'/content/drive/MyDrive/**/{pat}', recursive=True)
for h in sorted(set(hits)):
    print(f"   {os.path.getsize(h)/1048576:8.1f} MB  {h}")
if not hits:
    print("   드라이브에서 못 찾음")

print("\n[4] Colab 세션 저장소(/content)도 확인")
for h in glob.glob('/content/*.csv.gz') + glob.glob('/content/*.gz'):
    print(f"   {os.path.getsize(h)/1048576:8.1f} MB  {h}")

print("\n→ 위 [3]이나 [4]에 discharge_icu.csv.gz 가 보이면")
print("   설정 셀의 NOTES 를 그 경로로 그대로 바꾼다.")
print("→ 아무 데도 없으면 아직 업로드가 안 끝난 것이다. 226MB라 시간이 걸린다.")
