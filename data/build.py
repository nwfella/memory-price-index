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
# The page only ever shows the build DATE (DATA.generated_at.slice(0,10)). Inline the
# date part alone so the artifact is a pure function of the data: otherwise every run
# rewrites the minute in the payload, index.html never matches HEAD, and the
# "nothing changed, publish nothing" path can never trigger.
payload = payload.replace('"generated_at":"%s"' % ds["generated_at"],
                          '"generated_at":"%s"' % ds["generated_at"][:10])

# board timestamps: the vendor's own "Last Update" for each live board
board_asof = "not read on this build"
try:
    bord = json.load(open(os.path.join(HERE, "spot_board.json"), encoding="utf-8"))
    parts = [(b.get("as_of") or "").strip() for b in bord.get("boards", []) if b.get("as_of")]
    if parts:
        board_asof = " ; ".join(sorted(set(parts), reverse=True)[:2])   # already carries "(GMT+8)"
except Exception:
    pass

html = tpl.replace("/*__DATA__*/{}", payload)
html = (html.replace("{{RAM_DAYS}}", str(ram_days))
            .replace("{{RAM_KITS}}", str(kits))
            .replace("{{SPOT_POSTS}}", str(posts))
            .replace("{{BOARD_ASOF}}", board_asof)
            .replace("{{BUILT}}", ds["generated_at"][:10]))

assert "{{" not in html, "unreplaced placeholder: " + str(re.findall(r"\{\{[A-Z_]+\}\}", html))
assert "__DATA__" not in html
out = os.path.join(ROOT, "index.html")
open(out, "w", encoding="utf-8", newline="\n").write(html)
print(f"index.html {os.path.getsize(out)} bytes | {ram_days} retail days | {kits} kits | {posts} spot posts")
