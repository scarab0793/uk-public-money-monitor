"""Validate official source registry without inventing statistics."""
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
registry = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
assert registry["version"] == 1
ids = set()
for source in registry["sources"]:
    assert source["id"] not in ids, "Duplicate source ID"
    ids.add(source["id"])
    assert urlparse(source["url"]).scheme == "https", source["id"]
    assert urlparse(source["url"]).hostname, source["id"]
    assert source["scope"] in {"UK", "England", "Scotland", "Wales", "Northern Ireland"}
print(f"Validated {len(ids)} official source entries")
