import requests,json,time,datetime
from pathlib import Path
from urllib.parse import urljoin,urlparse
out=Path("data/procurement");out.mkdir(parents=True,exist_ok=True)
end=datetime.datetime.now(datetime.timezone.utc).date()
start=end-datetime.timedelta(days=7)
for name,url,prefix in [("contracts-finder","https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search","published"),("find-a-tender","https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages","updated")]:
    params={prefix+"From":str(start)+"T00:00:00Z",prefix+"To":str(end)+"T00:00:00Z","limit":100}
    if prefix=="updated": params={k:v.removesuffix("Z") if isinstance(v,str) else v for k,v in params.items()}
    records={};seen=set()
    while url:
        if url in seen: raise RuntimeError("Pagination loop")
        seen.add(url)
        for attempt in range(4):
            r=requests.get(url,params=params,timeout=90)
            if r.status_code not in (403,429,503): break
            time.sleep(int(r.headers.get("Retry-After","300")) if r.headers.get("Retry-After","300").isdigit() else 300)
        r.raise_for_status()
        package=r.json()
        for rel in package["releases"]:
            key=(rel["ocid"],rel["id"])
            records[key]=rel
        nxt=package.get("links",{}).get("next")
        if nxt:
            nxt=urljoin(url,nxt)
            if urlparse(nxt).hostname!=urlparse(url).hostname:raise RuntimeError("Unexpected pagination host")
        url=nxt;params=None
        time.sleep(3.2)
    if not records:raise RuntimeError("Empty source: "+name)
    rows=[]
    for (ocid,rid),r in records.items():
        tender=r.get("tender") or {}
        rows.append(dict(source=name,ocid=ocid,release_id=rid,date=r.get("date"),tags=r.get("tag",[]),buyer=(r.get("buyer") or {}).get("name"),title=tender.get("title"),description=tender.get("description"),tender_value=tender.get("value"),awards=r.get("awards",[]),contracts=r.get("contracts",[])))
    payload=dict(source=name,coverage_from=str(start),coverage_to_exclusive=str(end),basis="Publication/update window; distinct releases, not unique contracts or payments. Sources may overlap.",records=rows)
    (out/(name+".json")).write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    print(name,len(rows))
