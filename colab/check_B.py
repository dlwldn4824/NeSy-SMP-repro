import os, glob, subprocess
print('마운트:', os.path.isdir('/content/drive/MyDrive'))
if not os.path.isdir('/content/drive/MyDrive'):
    from google.colab import drive
    drive.mount('/content/drive', force_remount=True)
    print('재마운트:', os.path.isdir('/content/drive/MyDrive'))

for d in ['/content/drive/MyDrive', '/content']:
    print(f'\n--- {d} ---')
    try:
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                print(f'{os.path.getsize(p)/1e6:10.1f} MB  {f}')
    except Exception as e:
        print('  ', e)

print('\n--- 하위 폴더까지 comorb 검색 ---')
for p in glob.glob('/content/drive/MyDrive/**/*comorb*', recursive=True):
    print(f'{os.path.getsize(p)/1e6:10.1f} MB  {p}')
print(subprocess.run(['df','-h','/content/drive'],capture_output=True,text=True).stdout)
