@echo off
rem LK Terminal — 전 종목 분기 재무 DB 주간 갱신 (스케줄러가 매주 월요일 실행)
cd /d C:\Users\user99i1\buzztrend
rem 출력을 파일로 돌리면 코드페이지가 cp949 라 '—' 같은 글자에서 UnicodeEncodeError 로 죽는다.
rem histdb_update 는 첫 print 에서 죽어 2026-08-26 이후 한 번도 갱신 안 됨 (2026-10-21 발견).
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> data\findb\update.log
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe findb_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe histdb_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe capexdb_update.py --budget 10000 >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe yg_circle_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe yg_consensus_fn.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe cosmetics_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe customs_fetch.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe cosmetics_absvol_update.py >> data\findb\update.log 2>&1
git add data/findb/financials.csv.gz data/findb/meta.json data/histdb data/capexdb data/yg data/cosmetics >> data\findb\update.log 2>&1
git commit -m "findb weekly update" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >> data\findb\update.log 2>&1
git push >> data\findb\update.log 2>&1
