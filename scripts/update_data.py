#!/usr/bin/env python3
"""Fetch Taipower public outage files and write a normalized JSON snapshot.
No API key is required. Source formats can change; raw data is never interpreted as "no outage"
when a download fails.
"""
from __future__ import annotations
import csv, io, json, re, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outages.json"
EMERGENCY_URL = "https://service.taipower.com.tw/data/opendata/apply/file/d006012/001.xml"
PLANNED_ZIP_URL = "https://service.taipower.com.tw/data/opendata/apply/file/d077004/001.zip"

def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "TaiwanOutageMap/1.0 (public-data visualization)"})
    with urlopen(req, timeout=35) as resp:
        return resp.read()

def clean(v) -> str:
    if v is None: return ""
    return re.sub(r"\s+", " ", str(v)).strip()

def norm_key(v) -> str:
    return re.sub(r"[\s_\-（）()：:，,。/]+", "", clean(v)).lower()

def pick(row: dict, candidates: list[str]) -> str:
    lookup = {norm_key(k): v for k, v in row.items()}
    for c in candidates:
        value = lookup.get(norm_key(c))
        if value is not None and clean(value):
            return clean(value)
    # Flexible partial key matching for common government file headers.
    for k, v in lookup.items():
        if v is None or not clean(v): continue
        for c in candidates:
            ck = norm_key(c)
            if ck and (ck in k or k in ck): return clean(v)
    return ""

def county_town(text: str) -> tuple[str, str]:
    s = clean(text).replace("台", "臺")
    counties = ["臺北市","新北市","桃園市","臺中市","臺南市","高雄市","基隆市","新竹市","嘉義市",
                "新竹縣","苗栗縣","彰化縣","南投縣","雲林縣","嘉義縣","屏東縣","宜蘭縣","花蓮縣",
                "臺東縣","澎湖縣","金門縣","連江縣"]
    county = next((x for x in counties if x in s), "")
    town = ""
    if county:
        rest = s.split(county, 1)[1]
        m = re.search(r"([\u4e00-\u9fff]{1,6}(?:區|鄉|鎮|市))", rest)
        if m: town = m.group(1)
    else:
        m = re.search(r"([\u4e00-\u9fff]{2,5}[縣市])", s)
        if m: county = m.group(1)
    return county, town

def parse_emergency_xml(raw: bytes) -> list[dict]:
    events=[]
    root=ET.fromstring(raw)
    # XML may use attributes, namespaces, or slightly different tag labels.
    def local(tag): return tag.split("}")[-1]
    for node in root.iter():
        children={local(c.tag): clean(c.text) for c in list(node) if list(c)==[]}
        if not children: continue
        blob=" ".join(children.values())
        if not any(x in blob for x in ["停電","復電","災情"]): continue
        row={local(c.tag): clean(c.text) for c in list(node) if list(c)==[]}
        info=pick(row,["停電資訊","災害名稱","停電事件","事件名稱","名稱"])
        area=pick(row,["停電區域","停電範圍","影響區域","區域"])
        admin=pick(row,["行政區","行政區域","縣市鄉鎮"])
        households_raw=pick(row,["影響戶數","停電戶數","戶數"])
        try: households=int(re.sub(r"[^\d]", "", households_raw)) if households_raw else None
        except ValueError: households=None
        county,town=county_town(admin+" "+area)
        end=pick(row,["預計修復時間","預計復電時間","修復時間"])
        updated=pick(row,["資料更新時間","更新時間"])
        if not (info or area or admin): continue
        events.append({"type":"emergency","title":info or "天然災害停電資訊","county":county,"town":town,
                       "area":area,"households":households,"start":"","end":end,"source_updated":updated})
    # De-duplicate same records
    unique={}
    for e in events: unique[(e["title"],e["area"],e["county"],e["town"],e["households"])]=e
    return list(unique.values())

def decode_table(data: bytes, filename: str) -> list[dict]:
    # Try CSV encodings first.
    for enc in ("utf-8-sig","cp950","big5","utf-16"):
        try:
            text=data.decode(enc)
            sample=text[:3000]
            if "\x00" not in sample and ("," in sample or "\t" in sample):
                dialect=csv.Sniffer().sniff(sample, delimiters=",\t;")
                return [dict(r) for r in csv.DictReader(io.StringIO(text), dialect=dialect)]
        except Exception: pass
    # XLSX can be handled with openpyxl if available; XLS requires xlrd.
    suffix=Path(filename).suffix.lower()
    if suffix in (".xlsx",".xlsm"):
        try:
            import openpyxl
            wb=openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws=wb.active
            rows=list(ws.iter_rows(values_only=True))
            if not rows: return []
            headers=[clean(x) or f"col_{i}" for i,x in enumerate(rows[0])]
            return [dict(zip(headers, row)) for row in rows[1:] if any(x is not None for x in row)]
        except Exception as exc:
            print(f"Cannot parse workbook {filename}: {exc}", file=sys.stderr)
    if suffix==".xls":
        try:
            import xlrd
            wb=xlrd.open_workbook(file_contents=data); sh=wb.sheet_by_index(0)
            headers=[clean(sh.cell_value(0,c)) or f"col_{c}" for c in range(sh.ncols)]
            return [dict(zip(headers,sh.row_values(r))) for r in range(1,sh.nrows)]
        except Exception as exc:
            print(f"Cannot parse XLS {filename}: {exc}", file=sys.stderr)
    return []

def parse_planned_zip(raw: bytes) -> list[dict]:
    events=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if not n.endswith("/") and Path(n).suffix.lower() in (".csv",".txt",".xlsx",".xls",".xlsm")]
        for name in names:
            try: rows=decode_table(z.read(name),name)
            except Exception as exc:
                print(f"Skip {name}: {exc}", file=sys.stderr); continue
            for row in rows:
                title=pick(row,["工作概述","工作內容","工作項目","停電原因"])
                area=pick(row,["停電範圍","停電區域","影響地區","停電地址"])
                start=pick(row,["第一次停電時間","停電開始時間","開始時間","停電時間"])
                end=pick(row,["第二次停電時間","停電結束時間","結束時間"])
                admin=pick(row,["行政區","縣市","停電地區"])
                phone=pick(row,["查詢電話","電話"])
                county,town=county_town(admin+" "+area)
                if not (title or area or start): continue
                events.append({"type":"planned","title":title or "計畫性工作停電","county":county,"town":town,
                               "area":area,"households":None,"start":start,"end":end,"phone":phone})
    # De-duplicate
    unique={}
    for e in events: unique[(e["title"],e["area"],e["start"],e["end"])]=e
    return list(unique.values())

def main():
    events=[]; warnings=[]
    try:
        emergency=parse_emergency_xml(fetch(EMERGENCY_URL))
        events.extend(emergency)
        print(f"Emergency records: {len(emergency)}")
    except Exception as exc:
        warnings.append("災情停電來源下載／解析失敗")
        print(f"Emergency source failed: {exc}", file=sys.stderr)
    try:
        planned=parse_planned_zip(fetch(PLANNED_ZIP_URL))
        events.extend(planned)
        print(f"Planned records: {len(planned)}")
    except Exception as exc:
        warnings.append("施工停電來源下載／解析失敗")
        print(f"Planned source failed: {exc}", file=sys.stderr)

    # If both sources failed, fail the job and preserve the previous valid data.
    if len(warnings)==2:
        raise RuntimeError("Both official sources failed; refusing to overwrite the last good snapshot.")
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"source":"Taipower official open data",
             "events":events,"warnings":warnings,
             "notes":["官方公開資料未必涵蓋所有突發停電。","來源失敗或無事件不代表全台正常供電。"]}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Wrote {len(events)} events to {OUT}")

if __name__=="__main__":
    main()
