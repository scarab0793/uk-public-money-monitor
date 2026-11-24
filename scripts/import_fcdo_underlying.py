import requests, pathlib, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pandas as pd
import json
out=pathlib.Path("data/fcdo")
out.mkdir(parents=True,exist_ok=True)
manifest=[]
for year in (2024,2025):
    page=f"https://www.gov.uk/government/statistics/statistics-on-international-development-final-uk-oda-spend-{year}"
    r=requests.get(page,timeout=90);r.raise_for_status()
    links=BeautifulSoup(r.text,"html.parser").find_all("a",href=True)
    matches=[urljoin(page,a["href"]) for a in links if "data underlying" in a.get_text(" ",strip=True).lower() and ".ods" in a["href"].lower()]
    if not matches: raise RuntimeError(f"No underlying ODS for {year}")
    url=matches[0]
    response=requests.get(url,timeout=180);response.raise_for_status()
    path=out/f"oda-{year}.ods";path.write_bytes(response.content)
    book=pd.ExcelFile(path,engine="odf")
    for i,sheet in enumerate(book.sheet_names):
        df=book.parse(sheet,header=None)
        dest=out/f"oda-{year}-sheet-{i}.csv"
        df.to_csv(dest,index=False,header=False)
        manifest.append(dict(year=year,sheet=sheet,rows=len(df),columns=len(df.columns),file=str(dest),source=url))
    path.unlink()
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
