# -*- coding: utf-8 -*-
"""SPDR MSCI ACWI 보유종목(ISIN) → 거래소 티커 (OpenFIGI, 무료·키 없음: 분당 25요청 × 10건)."""
import json, time, warnings
import pandas as pd, requests, truststore
truststore.inject_into_ssl(); warnings.filterwarnings("ignore")
CC = {"United States": "US", "Japan": "JP", "China": "CH", "Hong Kong": "HK", "India": "IN", "Taiwan": "TT",
      "United Kingdom": "LN", "France": "FP", "Germany": "GY", "Canada": "CN", "Australia": "AU", "Brazil": "BZ",
      "Switzerland": "SW", "Netherlands": "NA", "Sweden": "SS", "Denmark": "DC", "Spain": "SM", "Italy": "IM",
      "Saudi Arabia": "AB", "South Africa": "SJ", "Mexico": "MM", "Indonesia": "IJ", "Thailand": "TB",
      "Malaysia": "MK", "Singapore": "SP", "Belgium": "BB", "Finland": "FH", "Norway": "NO", "Ireland": "ID",
      "Israel": "IT", "Poland": "PW", "Turkey": "TI", "Philippines": "PM", "New Zealand": "NZ", "Austria": "AV",
      "Portugal": "PL", "Greece": "GA", "Chile": "CI", "Hungary": "HB", "Czech Republic": "CP",
      "United Arab Emirates": "UH", "Qatar": "QD", "Kuwait": "KK", "Colombia": "CB", "Peru": "PE", "Egypt": "EY"}
x = pd.read_excel("spdr_acwi.xlsx", header=5)
x = x[x["ISIN"].astype(str).str.len() == 12]
x = x[x["Trade Country Name"] != "South Korea"].reset_index(drop=True)
out, jobs = [], []
for _, r in x.iterrows():
    j = {"idType": "ID_ISIN", "idValue": r["ISIN"]}
    if CC.get(r["Trade Country Name"]):
        j["exchCode"] = CC[r["Trade Country Name"]]
    jobs.append(j)
for i in range(0, len(jobs), 10):
    chunk = jobs[i:i + 10]
    for attempt in range(5):
        r = requests.post("https://api.openfigi.com/v3/mapping", json=chunk, timeout=60)
        if r.status_code == 200:
            break
        time.sleep(15)
    res = r.json() if r.status_code == 200 else [{}] * len(chunk)
    for j, rr in zip(chunk, res):
        d = rr.get("data") or []
        d = [z for z in d if z.get("marketSector") == "Equity"]
        t = d[0] if d else {}
        out.append({"ISIN": j["idValue"], "bb_ticker": t.get("ticker"), "bb_exch": t.get("exchCode"),
                    "sec_type": t.get("securityType"), "figi_name": t.get("name")})
    if (i // 10) % 20 == 0:
        print(i, "/", len(jobs), flush=True)
    time.sleep(2.6)
m = x.merge(pd.DataFrame(out).drop_duplicates("ISIN"), on="ISIN", how="left")
m.to_csv("acwi_members_raw.csv", index=False, encoding="utf-8-sig")
print("done", len(m), "mapped", m["bb_ticker"].notna().sum())
