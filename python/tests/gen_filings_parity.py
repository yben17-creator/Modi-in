"""Parity cases for the TS port of EdgarProvider.filing_flags + dilution_filings.
Usage: python tests/gen_filings_parity.py <out.json>   (filings are arbitrary test inputs, not company data)"""
import json, sys
from dataclasses import asdict
from datetime import date
sys.path.insert(0, '.')
from evi.providers.edgar import EdgarProvider as E

def f(form, filed, items=""):
    return {"form": form, "filingDate": filed, "acceptance": f"{filed}T16:05:00.000Z", "items": items, "url": f"https://x/{form}/{filed}"}

filings = [
    f("8-K", "2026-11-01", "2.02,9.01"), f("8-K", "2026-10-20", "5.02, 9.01"), f("8-K/A", "2026-09-15", "4.01"),
    f("8-K", "2026-08-01", "1.05,2.05,2.06"), f("8-K", "2026-06-01", "4.02"), f("8-K", "2026-03-01", "1.03,3.01"),
    f("8-K", "2025-12-01", "2.04"), f("8-K", "2025-11-10", "3.02"), f("8-K", "2025-11-20", "1.02"),
    f("NT 10-K", "2026-03-31"), f("NT 10-Q", "2025-05-15"), f("SC 13D", "2026-10-30"), f("SCHEDULE 13D", "2026-07-07"),
    f("S-3", "2024-01-10"), f("S-3ASR", "2023-12-01"), f("F-3", "2026-02-02"), f("S-3/A", "2025-06-06"),
    f("424B5", "2026-05-05"), f("424B2", "2025-10-01"), f("424B3", "2026-11-10"), f("10-K", "2026-02-20"), f("4", "2026-11-12"),
]
out = []
for today in ("2026-11-14", "2025-12-31", "2024-02-01"):
    t = date.fromisoformat(today)
    out.append({"today": today, "flags": [asdict(x) for x in E.filing_flags(filings, t)],
                "flags_short": [asdict(x) for x in E.filing_flags(filings, t, lookback_days=90, known_after_days=10)],
                "dilution": E.dilution_filings(filings, t)})
json.dump({"filings": filings, "cases": out}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c in out: print(c["today"], len(c["flags"]), len(c["flags_short"]), c["dilution"]["has_shelf"], c["dilution"]["has_recent_offering"])
