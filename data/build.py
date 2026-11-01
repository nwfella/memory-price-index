"""Inject data/dataset.json into template.html -> index.html (single file, no fetch)."""
import json, os, datetime, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ds = json.load(open(os.path.join(HERE, "dataset.json"), encoding="utf-8"))
tpl = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()

ram_days = len(ds["series"]["ddr5_retail"]["pts"]) if len(ds["series"]["ddr5_retail"]["pts"]) > len(ds["series"]["ddr4_retail"]["pts"]) else len(ds["series"]["ddr4_retail"]["pts"])
ram_days = max(len(ds["series"]["ddr5_retail"]["pts"]), len(ds["series"]["ddr4_retail"]["pts"]))
kits = ds["series"]["ddr5_retail"]["kits"][-1][1]
posts = len(ds["source_posts"])

payload = json.dumps(ds, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
html = tpl.replace("/*__DATA__*/{}", payload)
html = (html.replace("{{RAM_DAYS}}", str(ram_days))
            .replace("{{RAM_KITS}}", str(kits))
            .replace("{{SPOT_POSTS}}", str(posts))
            .replace("{{BUILT}}", ds["generated_at"][:10]))

assert "{{" not in html, "unreplaced placeholder: " + str(re.findall(r"\{\{[A-Z_]+\}\}", html))
assert "__DATA__" not in html
out = os.path.join(ROOT, "index.html")
open(out, "w", encoding="utf-8", newline="\n").write(html)
print(f"index.html {os.path.getsize(out)} bytes | {ram_days} retail days | {kits} kits | {posts} spot posts")
