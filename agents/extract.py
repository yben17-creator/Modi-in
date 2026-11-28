"""Compact per-agent view of a dossier folder (code, not the model, selects the fields).
Raw dossiers are ~50 KB each (~1 MB for 20); this view is ~0.5 KB per company, so a Maestro run fits the subscription.
Usage: python3 agents/extract.py <earnings-insight>/dossiers/<date>
"""
import json, sys, os
ab = {"positive": "+", "negative": "-"}
d0 = sys.argv[1]
idx = json.load(open(os.path.join(d0, "index.json")))
for t in idx["tickers"]:
    d = json.load(open(os.path.join(d0, f"{t}.json"))); a = d["auditor"]; L = a["leading"]; dl = d["delta"]; e = dl["expectations"] or {}
    lead = " ".join(f"{x['key']}{ab[x['direction']]}" for x in L["signals"] if x["direction"] in ab)
    fl = [f"{f['date']}:{f['category']}:{f['severity']}" for f in a["flags"] if f["severity"] >= 3 or f.get("structural")][-3:]
    ins = a["insiders"] or {}; nr = d["nextReport"]
    print(f"## {d['rank']['position']}. {t} | sector {d['sector']} | px {d['price']} @{d['priceDate']} | filed {d['fundamentalsFiled']} | next {nr['date'] if nr else None} ({nr['daysAway'] if nr else ''}d) | missing {d['missing']}")
    print(f"  AUDITOR health {a['health']} risk {a['risk']['score']} override {a['risk']['override']} gate {a['gate']['pass']} | lead {L['positives']}+/{L['negatives']}- {lead} | flags>=3 {fl} | insiders buys {ins.get('buys')} sells {ins.get('sells')} openSell ${round((ins.get('openSellValue') or 0)/1e6,1)}M unusual {len(ins.get('unusual') or [])}")
    print(f"  DELTA gap {dl['gap']['score']} {[(p['key'], p['value']) for p in dl['gap']['parts']]} | valuation {dl['valuation']['score']} mos {round(dl['valuation']['mos'] or 0, 2)} mid {round(dl['valuation']['mid'] or 0, 1)} | implied {round(e.get('implied') or 0, 3)} predicted {e.get('predicted', {}).get('g')} basis {e.get('predicted', {}).get('base')}")
