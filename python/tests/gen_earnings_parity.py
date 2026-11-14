"""Parity cases for the TS port of EdgarProvider.earnings_events + estimate_next_earnings.
Usage: python tests/gen_earnings_parity.py <out.json>   (dates are arbitrary test inputs, not company data)"""
import json, sys
from datetime import date
sys.path.insert(0, '.')
from evi.providers.edgar import EdgarProvider as E

def f(form, filed, items="2.02,9.01", acc=None):
    return {"form": form, "filingDate": filed, "acceptance": acc if acc is not None else f"{filed}T16:05:00.000Z", "items": items, "url": f"u/{filed}/{form}"}

quarterly = [f("8-K", d) for d in ("2024-01-25", "2024-04-25", "2024-07-30", "2024-10-24", "2025-01-29", "2025-04-24", "2025-07-30", "2025-10-29")]
cases_in = {
    "regular_quarterly_with_noise": quarterly + [f("8-K", "2025-03-01", "5.02"), f("8-K/A", "2025-05-01"), f("10-Q", "2025-04-30", ""),
                                                 f("8-K", "2025-07-30", "2.02", acc="2025-07-30T20:01:00.000Z")],
    "too_few_events": quarterly[:2],
    "irregular_gaps_only": [f("8-K", d) for d in ("2023-01-10", "2023-02-01", "2023-12-20", "2024-01-05")],
    "old_history_rolls_forward": [f("8-K", d) for d in ("2021-02-10", "2021-05-11", "2021-08-10", "2021-11-09")],
    "item_substring_not_matched": [f("8-K", d, "12.02") for d in ("2025-01-29", "2025-04-24", "2025-07-30")],
    "no_acceptance_uses_filed": [f("8-K", d, acc="") for d in ("2025-03-05", "2025-06-04", "2025-09-03")],
}
todays = ["2025-11-14", "2026-02-20", "2026-11-14"]
out = []
for name, filings in cases_in.items():
    ev = E.earnings_events(filings)
    for t in todays:
        est = E.estimate_next_earnings(ev, date.fromisoformat(t))
        out.append({"name": f"{name}@{t}", "filings": filings, "today": t,
                    "events": ev, "estimate": est})
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(len(out), "cases")
for c in out: print(c["name"], c["estimate"] and c["estimate"]["date"])
