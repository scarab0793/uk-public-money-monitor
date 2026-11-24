import csv,json,collections
from pathlib import Path
from decimal import Decimal
base=Path("data/fcdo")
out=Path("data/fcdo-normalized")
out.mkdir(exist_ok=True)
source=max((x for x in json.loads((base/"manifest.json").read_text()) if x["sheet"]=="Data"),key=lambda x:x["year"])
projects={}; groups=collections.defaultdict(lambda:[0,Decimal(0)]); total=Decimal(0); count=0
with Path(source["file"]).open(encoding="utf-8",newline="") as f:
 for r in csv.DictReader(f):
  y=int(r["Year"]); a=r["ExtendingAgencyText"].strip(); i=r["ActivityIdentifier"].strip(); c=r["RecipientCountryText"].strip()
  v=Decimal(r["HeadlineMeasureofODA"].strip())*1000
  count+=1; total+=v
  p=projects.setdefault((a,i),dict(agency=a,activity_id=i,titles=set(),descriptions=set(),countries=set(),years={}))
  p["titles"].add(r["ProjectTitle"].strip());p["descriptions"].add(r["ProjectDescription"].strip());p["countries"].add(c)
  p["years"][y]=p["years"].get(y,Decimal(0))+v
  for k,label in [("country",c),("agency",a),("sector",r["BroadSectorText"]),("year",str(y))]:
   g=groups[k,y,label];g[0]+=1;g[1]+=v
def dump(path,obj):
 path.write_text(json.dumps(obj,ensure_ascii=False,default=lambda x:sorted(x) if isinstance(x,set) else str(x),separators=(",",":")),encoding="utf-8")
assert sum(sum(p["years"].values()) for p in projects.values())==total
for k in ("country","agency","sector","year"):
 assert sum(v[1] for key,v in groups.items() if key[0]==k)==total
 dump(out/(k+".json"),[dict(year=y,category=l,rows=v[0],oda_gbp=v[1]) for (t,y,l),v in sorted(groups.items()) if t==k])
items=list(projects.values()); index=[]
for start in range(0,len(items),500):
 name=f"projects-{start//500}.json"; batch=items[start:start+500];dump(out/name,batch)
 for j,p in enumerate(batch):index.append(dict(file=name,offset=j,agency=p["agency"],activity_id=p["activity_id"],titles=sorted(p["titles"]),countries=sorted(p["countries"]),years=p["years"]))
dump(out/"index.json",index)
dump(out/"audit.json",dict(source=source,rows=count,project_groups=len(items),oda_gbp=total,basis="Latest source vintage only; all source rows retained; agency and activity identifier grouping; nominal GBP headline ODA."))
print(count,len(items),total)
