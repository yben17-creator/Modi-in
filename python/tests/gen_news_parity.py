"""Parity cases for the TS port of providers/finnhub.py news_flags (headline keyword red flags).
Usage: TZ=UTC python tests/gen_news_parity.py <out.json>   (synthetic headlines, not real news)"""
import json, sys, time
from datetime import date, datetime, timezone
sys.path.insert(0, '.')
from evi.providers.finnhub import FinnhubProvider

def ts(d): return int(datetime(*d, 15, 0, tzinfo=timezone.utc).timestamp())

NEWS = [
    {"datetime": ts((2026, 11, 13)), "headline": "Kanzhun Lowers Guidance for Fourth Quarter as Hiring Slows", "summary": "", "source": "Wire", "url": "https://example.test/1"},
    {"datetime": ts((2026, 11, 13)), "headline": "Another story: company cuts outlook", "summary": "", "source": "Wire", "url": "https://example.test/2"},
    {"datetime": ts((2026, 11, 2)), "headline": "Shareholder class action filed", "summary": "Law firm announces lawsuit", "source": "PR", "url": "https://example.test/3"},
    {"datetime": ts((2026, 10, 1)), "headline": "CEO steps down effective immediately", "summary": "", "source": "Wire", "url": None},
    {"datetime": ts((2026, 9, 20)), "headline": "Company announces ATM program", "summary": "at-the-market offering of up to $100M", "source": "Wire", "url": "https://example.test/5"},
    {"datetime": ts((2026, 9, 1)), "headline": "Quarterly results beat estimates", "summary": "Revenue grew 20%", "source": "Wire", "url": "https://example.test/6"},
    {"datetime": ts((2026, 8, 30)), "headline": "Price war intensifies in the sector", "summary": "", "source": "Blog", "url": "https://example.test/7"},
    {"datetime": ts((2026, 11, 10)), "headline": "SEC INVESTIGATION into accounting; material weakness disclosed", "summary": "", "source": "Wire", "url": "https://example.test/8"},
    {"datetime": ts((2026, 11, 14)), "headline": "Auditor resigns? no — auditor quits after dispute", "summary": "", "source": "Wire", "url": "https://example.test/9"},
    {"headline": "missing datetime defaults to epoch", "summary": "data breach", "source": "X"},
]

class P(FinnhubProvider):
    def __init__(self, js): self.js = js; self.unavailable = set()
    def _get(self, path, ttl_h=None, **params): return self.js

cases = []
for name, js, today, days, known in [("mixed", NEWS, date(2026, 11, 15), 90, 7), ("short_window", NEWS, date(2026, 11, 15), 10, 3),
                                     ("empty", [], date(2026, 11, 15), 90, 7), ("none", None, date(2026, 11, 15), 90, 7)]:
    flags = P(js).news_flags("TST", today, days, known)
    cases.append({"name": name, "js": js, "today": today.isoformat(), "days": days, "known_after_days": known,
                  "out": [f.__dict__ for f in flags]})
json.dump({"cases": cases}, open(sys.argv[1], "w"), ensure_ascii=False)
for c in cases: print(c["name"], [(f["category"], f["date"], f["known"]) for f in c["out"]])
