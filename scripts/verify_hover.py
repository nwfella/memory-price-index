#!/usr/bin/env python3
"""Regression gate: the chart must repaint its frame, not stack crosshairs.

Sweeps ~61 synthetic mousemoves across the main chart in headless Chrome and
counts how many canvas columns are painted with the crosshair stroke.
A correct build leaves exactly ONE. The smear bug produced ~59 (and never
cleared on mouseleave).

    python scripts/verify_hover.py            # exit 0 = pass
    python scripts/verify_hover.py --keep     # keep the probe html for inspection
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "index.html")

CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

PROBE = """
<script>
function crosshairColumns(cv) {
  const ctx = cv.getContext("2d");
  const w = cv.width, h = cv.height;
  const d = ctx.getImageData(0, 0, w, h).data;
  let cols = 0;
  for (let x = 0; x < w; x++) {
    let n = 0;
    for (let y = 0; y < h; y++) {
      const i = (y * w + x) * 4;
      // canvas is transparent; getImageData is UNPREMULTIPLIED:
      // crosshair rgba(232,237,245,.30) reads back as ~(232,237,245, a=76)
      if (d[i+3] > 35 && d[i+3] < 140 && d[i] > 200 &&
          Math.abs(d[i]-d[i+1]) < 18 && Math.abs(d[i+1]-d[i+2]) < 26) n++;
    }
    if (n > h * 0.55) cols++;
  }
  return cols;
}
window.addEventListener("load", () => setTimeout(() => {
  const cv = document.getElementById("mainChart");
  if (!cv) { document.title = JSON.stringify({error: "no #mainChart"}); return; }
  const r = cv.getBoundingClientRect();
  const y = r.top + r.height / 2;
  const noHover = crosshairColumns(cv);
  for (let i = 0; i <= 60; i++) {
    cv.dispatchEvent(new MouseEvent("mousemove", {
      clientX: r.left + 60 + (r.width - 90) * (i / 60), clientY: y, bubbles: true}));
  }
  cv.dispatchEvent(new MouseEvent("mousemove", {
    clientX: r.left + r.width * 0.62, clientY: y, bubbles: true}));
  const afterSweep = crosshairColumns(cv);
  cv.dispatchEvent(new MouseEvent("mouseleave", {bubbles: true}));
  const afterLeave = crosshairColumns(cv);
  const tip = document.getElementById("tip");
  document.title = JSON.stringify({
    noHover, afterSweep, afterLeave,
    tooltipVisible: !!tip && tip.textContent.length > 8,
    tooltipText: tip ? tip.textContent.slice(0, 32) : ""
  });
}, 1200));
</script>
"""


def chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for pat in (r"C:/Program Files*/Google/Chrome/Application/chrome.exe",
                r"C:/Program Files*/Microsoft/Edge/Application/msedge.exe"):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def main():
    exe = chrome()
    if not exe:
        print("[skip] no Chrome/Edge found — hover gate not run")
        return 0

    html = open(INDEX, encoding="utf-8").read()
    if "<title>Memwatch" not in html:
        print("[FAIL] index.html does not look like the built page")
        return 1

    tmpdir = tempfile.mkdtemp(prefix="memwatch-hover-")
    probe_html = os.path.join(tmpdir, "probe.html")
    open(probe_html, "w", encoding="utf-8").write(html.replace("</body>", PROBE + "</body>"))
    profile = os.path.join(tmpdir, "profile")

    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--user-data-dir=" + profile, "--window-size=1400,1000",
           "--virtual-time-budget=6000", "--dump-dom", "file:///" + probe_html.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    m = re.search(r"<title>([^<]*)</title>", r.stdout or "")
    if not m:
        print("[FAIL] headless run produced no DOM (chrome rc=%s)" % r.returncode)
        return 1
    try:
        res = json.loads(m.group(1).replace("&quot;", '"'))
    except Exception:
        print("[FAIL] could not parse probe result: %r" % m.group(1)[:120])
        return 1
    if "error" in res:
        print("[FAIL] %s" % res["error"])
        return 1

    ok = (res["afterSweep"] == 1 and res["noHover"] == 0 and res["afterLeave"] == 0
          and res.get("tooltipVisible"))
    msg = ("crosshair columns: idle=%d after 61 moves=%d after leave=%d | tooltip=%s %r"
           % (res["noHover"], res["afterSweep"], res["afterLeave"],
              res.get("tooltipVisible"), res.get("tooltipText", "")))
    if ok:
        print("[ok] hover repaint gate passed — " + msg)
        return 0
    print("[FAIL] hover repaint gate: " + msg)
    print("       expected exactly 1 crosshair column after the sweep, 0 idle and after leave.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
