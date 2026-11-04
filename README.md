# Memwatch — DRAM, NAND & SSD price history

Live: **https://nwfella.github.io/memory-price-index/**

A single-file dashboard tracking the 2025–2026 memory supercycle from four angles at once, with every
point traceable to a dated public source. No build step, no dependencies, no runtime fetches — the data
is baked into the page.

![status](https://img.shields.io/badge/data%20through-2026--11--01-f5b845)
![license](https://img.shields.io/badge/license-MIT-blue)

## What it tracks

| Series | Unit | Cadence | Source |
|---|---|---|---|
| DDR5 desktop kits (retail) | $/GB | daily | [RamRadar RAM Price Index](https://ramradar.app/ram-price-index) |
| DDR4 desktop kits (retail) | $/GB | daily | RamRadar |
| DDR4 8Gb chip (spot) | $/chip | weekly | [TrendForce memory spot](https://www.trendforce.com/price/dram/dram_spot) |
| 512Gb TLC NAND wafer (spot) | $/wafer | weekly | [TrendForce wafer spot](https://www.trendforce.com/price/flash/wafer_spot) |
| Client SSD OEM contract | $/drive | quarterly | TrendForce PC-client OEM SSD contract price |

## The read (1 Nov 2026)

- **NAND has turned.** 512Gb TLC wafers peaked at **$23.00** on 18 Mar 2026, held $19–21 for five months,
  then broke: **−26.6% off peak**, −15.1% in 30 days, −9.19% in the week to 26 Oct. Wafer contract prices
  stopped rising in October after 21 consecutive monthly increases.
- **DRAM has not.** The DDR4 8Gb benchmark chip printed a record **$47.04** with **zero** drawdown. TrendForce
  still guides conventional DRAM contract **+10–15% QoQ** for 4Q26 as HBM and server capacity crowd out
  consumer wafers.
- **Retail is the last to move.** DDR5 kits are −2.6% off their 23 Oct record and DDR4 kits −3.5% off April —
  first cracks, not a trend. Client SSD contract prices are still rising (+285–303% YoY for 256GB) but the
  increases are narrowing; 4Q26 client SSD guidance is "limited increase".

## Why it looks the way it does

- **Index mode rebases every series to 100 at the window start.** A chip sold by the wafer and a kit sold by
  the gigabyte are not comparable in dollars; they are comparable in multiples.
- **The drawdown chart is the honest answer to "is it coming down".** Zero means today is the record.
- **Nothing is interpolated.** Missing weeks stay missing; lines connect observations that exist.
- **Discontinuities are annotated, not smoothed.** The vertical marker in May 2026 is a listing-mix change in
  the upstream retail index (the cheapest tracked DDR5 kit jumped $3.17 → $6.77/GB as cheap listings aged
  out), not an overnight price cut. Days with fewer than 10 tracked kits are excluded.
- **No invented numbers.** The SSD ladder shows a prior-quarter delta only where a prior quarter actually
  exists in the dataset; the other two tiers show actuals and say so.

## Automation

A Hermes cron job (`Memwatch daily refresh`, 07:40 local) runs `scripts/daily_refresh.py` every day with
no LLM in the loop:

1. re-download the retail index, re-discover and re-parse the weekly spot posts
2. **guard:** if the TrendForce re-parse degrades, the last good `spot_series.csv` is restored — one bad
   upstream day cannot wipe 12 months of history off the chart
3. **gate:** the rebuilt page must pass size + marker checks or nothing is deployed
4. **hover gate:** `scripts/verify_hover.py` sweeps 61 synthetic mousemoves across the chart in headless Chrome
   and asserts exactly one crosshair column is painted (idle 0, after sweep 1, after leave 0). The smear bug this
   catches drew 59 stacked lines and never cleared them
5. **publish:** commit `index.html` + `data/dataset.json` and push (non-interactive git, network-only retries),
   then poll Pages until the live bytes match the pushed bytes
6. **quiet:** if the material data is unchanged, the run publishes nothing and restores its worktree

Stdout is the daily report — one line, e.g.
`memwatch 2026-11-04 — DDR5 $19.49/GB (+11.0% 30d), DDR4 chip $46.82, NAND 512Gb $16.15 (-29.8% off peak). Published 2da6cad — live verified`

## Rebuild

```bash
python data/refresh.py
```

1. re-downloads the RamRadar daily CSV
2. re-fetches and re-parses every TrendForce weekly spot post listed in `data/spot_urls.txt`
3. rebuilds `data/dataset.json` (stats, drawdown, annotations)
4. rebuilds `index.html` with the data inlined

To add a week, append the post URL to `data/spot_urls.txt`
(`trendforce.com/news/YYYY/MM/DD/insights-memory-spot-price-update-*`). TrendForce revises old posts, so the
whole list is re-parsed each run.

```
data/
  ramradar.csv          raw daily retail index (as downloaded)
  spot_urls.txt         the 42 TrendForce posts feeding the spot series (auto-extended on refresh)
  spot_series.csv       parsed weekly quotes (one row per post, with URL)
  fetch_spot_quotes.py  parser for the weekly posts
  build_dataset.py      joins everything, computes stats + marks
  build.py              template + data -> index.html
  refresh.py            the four steps above, in order
template.html           markup/CSS/JS with a /*__DATA__*/ placeholder
index.html              the deployed artifact (generated — edit the template)
```

## Limits

Retail figures are **asking prices**, not transactions: RamRadar records the lowest live listing per kit from
eBay/Newegg (B&H until Sep 2026), so an open-box item can enter the pool and coverage is eBay-weighted. Spot
is a thin, broker-driven market for loose chips; contract is what OEMs pay quarterly. Spot moves first and
overshoots — a falling wafer quote leads SSD pricing by weeks to months, it does not mean a specific drive got
cheaper today. Not investment advice.

## License

MIT © nwfella. See [LICENSE](LICENSE).
