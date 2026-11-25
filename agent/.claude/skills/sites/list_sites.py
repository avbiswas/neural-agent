"""List the hosted sites: name, URL, last update, title and description."""
import os
import re
from datetime import datetime
from pathlib import Path

SITES = Path(__file__).resolve().parents[3] / "sites"   # agent/sites
BASE_URL = os.environ.get("SITES_URL", "http://127.0.0.1:8080").rstrip("/")

sites = sorted(SITES.glob("*/index.html")) if SITES.exists() else []
if not sites:
    print("No sites yet.")

for index in sites:
    html = index.read_text(errors="ignore")
    title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    description = re.search(r'<meta\s+name="description"\s+content="(.*?)"', html, re.S | re.I)
    updated = datetime.fromtimestamp(max(f.stat().st_mtime for f in index.parent.rglob("*")))
    print(f"{index.parent.name}\n"
          f"  url:         {BASE_URL}/{index.parent.name}/\n"
          f"  updated:     {updated:%Y-%m-%d %H:%M}\n"
          f"  title:       {title.group(1).strip() if title else '-'}\n"
          f"  description: {description.group(1).strip() if description else '-'}")
