@echo off
rem LK Terminal — 전 종목 분기 재무 DB 주간 갱신 (스케줄러가 매주 월요일 실행)
cd /d C:\Users\user99i1\buzztrend
echo ===== %date% %time% ===== >> data\findb\update.log
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe findb_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe histdb_update.py >> data\findb\update.log 2>&1
C:\Users\user99i1\AppData\Local\Programs\Python\Python312\python.exe capexdb_update.py --budget 10000 >> data\findb\update.log 2>&1
git add data/findb/financials.csv.gz data/findb/meta.json data/histdb data/capexdb >> data\findb\update.log 2>&1
git commit -m "findb weekly update" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" >> data\findb\update.log 2>&1
git push >> data\findb\update.log 2>&1
