"""One-command refresh: pull fresh sources, rebuild the dataset, rebuild index.html.

    python data/refresh.py

Steps
  1. re-download the RamRadar daily RAM index CSV
  2. re-fetch + re-parse every TrendForce weekly spot post listed in spot_urls.txt
  3. rebuild data/dataset.json  (stats, drawdown, marks)
  4. rebuild index.html         (data baked in — the page never fetches at runtime)

Adding a new week: append the new post URL to data/spot_urls.txt
(pattern: trendforce.com/news/YYYY/MM/DD/insights-memory-spot-price-update-*).
TrendForce also revises older posts, so re-parsing the whole list keeps history honest.
"""
import os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
RAMRADAR = "https://ramradar.app/ram-price-index/data.csv"


def step(msg):
    print("\n== " + msg)


def run(script):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        sys.exit("FAILED: " + script)
    lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
    for l in lines[:6]:
        print("   " + l)
    if len(lines) > 6:
        print("   ... " + lines[-1])


step("1/4  downloading RamRadar daily index")
req = urllib.request.Request(RAMRADAR, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=60) as r:
    body = r.read()
if len(body) < 10000 or b"date,ram_type" not in body[:200]:
    sys.exit("RamRadar CSV looks wrong (%d bytes) — refusing to overwrite" % len(body))
open(os.path.join(HERE, "ramradar.csv"), "wb").write(body)
print("   %d bytes, %d rows" % (len(body), body.count(b"\n")))

step("2/4  re-parsing TrendForce weekly spot posts")
run("fetch_spot_quotes.py")

step("3/4  building dataset")
run("build_dataset.py")

step("4/4  building index.html")
run("build.py")

print("\nDone. Commit index.html (+ data/dataset.json) to publish.")
