"""SEC EDGAR provider — the primary source for fundamentals, filings, insider trades and dilution events.

Endpoints (free; SEC requires a descriptive User-Agent with contact e-mail and ≤10 requests/second):
  https://www.sec.gov/files/company_tickers_exchange.json
  https://data.sec.gov/submissions/CIK##########.json   (+ older pages listed in filings.files)
  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
  https://www.sec.gov/Archives/edgar/data/<cik>/<accession>/<doc>   (Form 4 XML)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any

from ..http import CachedHttp
from ..models import Flag, InsiderTx
from ..store import Store

SEC = "SEC EDGAR"

# 8-K items → (category, Hebrew title, severity 1–4, structural?)
ITEM_FLAGS: dict[str, tuple[str, str, int, bool]] = {
    "1.02": ("Customer/Contract Loss", "סיום הסכם מהותי (Item 1.02)", 2, False),
    "1.03": ("Bankruptcy", "פשיטת רגל / כינוס (Item 1.03)", 4, True),
    "1.05": ("Cybersecurity Incident", "אירוע סייבר מהותי (Item 1.05)", 3, False),
    "2.04": ("Debt Acceleration", "אירוע המאיץ התחייבות פיננסית (Item 2.04)", 4, False),
    "2.05": ("Restructuring", "עלויות ארגון מחדש / פיטורים (Item 2.05)", 2, False),
    "2.06": ("Impairment", "ירידת ערך מהותית (Item 2.06)", 3, False),
    "3.01": ("Delisting Notice", "הודעת מחיקה / אי-עמידה בכללי הבורסה (Item 3.01)", 4, False),
    "3.02": ("Share Dilution", "מכירת מניות לא רשומות (Item 3.02)", 2, False),
    "4.01": ("Auditor Change", "החלפת / התפטרות רואה החשבון המבקר (Item 4.01)", 3, False),
    "4.02": ("Accounting Issues", "אי-הסתמכות על דוחות כספיים קודמים — הצגה מחדש (Item 4.02)", 4, False),
    "5.02": ("Executive Departure", "שינוי בדירקטורים / נושאי משרה (Item 5.02)", 2, False),
}
FORM_FLAGS: dict[str, tuple[str, str, int]] = {
    "NT 10-K": ("Late Filing", "הודעה על איחור בהגשת דוח שנתי (NT 10-K)", 3),
    "NT 10-Q": ("Late Filing", "הודעה על איחור בהגשת דוח רבעוני (NT 10-Q)", 3),
    "SC 13D": ("Activist / Control", "החזקה אקטיביסטית מעל 5% (SC 13D)", 1),
    "SCHEDULE 13D": ("Activist / Control", "החזקה אקטיביסטית מעל 5% (Schedule 13D)", 1),
}
SHELF_FORMS = {"S-3", "S-3ASR", "F-3", "F-3ASR", "S-3/A"}
OFFERING_FORMS = {"424B5", "424B2", "424B3", "424B4", "424B7"}
FORM4 = {"4", "4/A"}

TX_CODES = {"S": "sell", "P": "buy", "F": "tax", "M": "other", "A": "other", "G": "other", "D": "other", "C": "other", "X": "other"}


class EdgarProvider:
    name = SEC

    def __init__(self, store: Store, user_agent: str, per_second: float = 8, ttl: dict[str, float] | None = None):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT חסר או לא תקין. SEC דורש 'Name email@example.com' בקובץ .env")
        self.http = CachedHttp(store, "edgar", per_second, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.ttl = {"tickers": 168, "submissions": 12, "companyfacts": 24, "form4": 24 * 30, **(ttl or {})}
        self._tickers: dict[str, dict] | None = None

    # ------------------------------------------------------------ directory
    def tickers(self) -> dict[str, dict]:
        """ticker → {cik, name, exchange}"""
        if self._tickers is None:
            js = self.http.get_json("https://www.sec.gov/files/company_tickers_exchange.json", ttl_h=self.ttl["tickers"])
            fields = js["fields"]
            out = {}
            for row in js["data"]:
                d = dict(zip(fields, row))
                if d.get("ticker"):
                    out[d["ticker"].upper()] = {"cik": int(d["cik"]), "name": d["name"], "exchange": d.get("exchange")}
            self._tickers = out
        return self._tickers

    def fetched_at(self, url: str) -> str | None:
        return self.http.fetched_at(url)

    @staticmethod
    def _cik10(cik: int) -> str:
        return f"CIK{cik:010d}"

    def companyfacts(self, cik: int) -> tuple[dict | None, str]:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/{self._cik10(cik)}.json"
        return self.http.get_json(url, ttl_h=self.ttl["companyfacts"]), url

    def submissions(self, cik: int, include_older: bool = True, min_year: int | None = None) -> tuple[dict | None, list[dict]]:
        """Returns (header, filings[]) where filings are dicts with form, filingDate, acceptanceDateTime, items, url."""
        url = f"https://data.sec.gov/submissions/{self._cik10(cik)}.json"
        js = self.http.get_json(url, ttl_h=self.ttl["submissions"])
        if not js:
            return None, []
        filings = self._flatten(js["filings"]["recent"], cik)
        if include_older:
            for f in js["filings"].get("files", []):
                if min_year and f.get("filingTo", "9999")[:4] < str(min_year):
                    continue
                older = self.http.get_json(f"https://data.sec.gov/submissions/{f['name']}", ttl_h=24 * 7)
                if older:
                    filings.extend(self._flatten(older, cik))
        header = {k: js.get(k) for k in ("cik", "name", "sic", "sicDescription", "tickers", "exchanges", "fiscalYearEnd")}
        header["_url"] = url
        return header, filings

    @staticmethod
    def _flatten(block: dict, cik: int) -> list[dict]:
        n = len(block.get("accessionNumber", []))
        out = []
        for i in range(n):
            acc = block["accessionNumber"][i]
            doc = block.get("primaryDocument", [""] * n)[i] or ""
            out.append({
                "accession": acc,
                "form": block["form"][i],
                "filingDate": block["filingDate"][i],
                "acceptance": (block.get("acceptanceDateTime") or [""] * n)[i],
                "items": (block.get("items") or [""] * n)[i] or "",
                "doc": doc,
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}" if doc else
                       f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/",
            })
        return out

    # ------------------------------------------------------------ earnings announcements (8-K Item 2.02)
    @staticmethod
    def earnings_events(filings: list[dict]) -> list[dict]:
        ev = []
        seen = set()
        for f in filings:
            if f["form"] in ("8-K", "8-K/A") and "2.02" in f["items"].split(","):
                if f["form"] == "8-K/A" or f["filingDate"] in seen:
                    continue
                seen.add(f["filingDate"])
                ev.append({"accepted": f["acceptance"] or f["filingDate"], "filed": f["filingDate"], "url": f["url"]})
        return sorted(ev, key=lambda e: e["accepted"])

    @staticmethod
    def estimate_next_earnings(events: list[dict], today: date) -> dict | None:
        """Local estimate: last 2.02 date + median interval (≈91 days). Labeled ESTIMATED."""
        if len(events) < 3:
            return None
        ds = [date.fromisoformat(e["filed"]) for e in events[-8:]]
        gaps = sorted((b - a).days for a, b in zip(ds, ds[1:]) if 60 <= (b - a).days <= 120)
        if not gaps:
            return None
        med = gaps[len(gaps) // 2]
        nxt = ds[-1] + timedelta(days=med)
        while nxt < today - timedelta(days=3):
            nxt += timedelta(days=med)
        # same quarter last year is usually a better anchor than the median interval
        yago = [d for d in ds if 330 <= (nxt - d).days <= 400]
        if yago:
            nxt = yago[-1] + timedelta(days=364)
            while nxt < today - timedelta(days=3):
                nxt += timedelta(days=91)
        return {"date": nxt.isoformat(), "status": "estimated_local",
                "basis": f"הערכה מקומית: מועד הדוח המקביל אשתקד / מרווח חציוני {med} ימים בין דוחות 8-K Item 2.02"}

    # ------------------------------------------------------------ red flags from filings
    @staticmethod
    def filing_flags(filings: list[dict], today: date, lookback_days: int = 365, known_after_days: int = 30) -> list[Flag]:
        flags: list[Flag] = []
        cutoff = (today - timedelta(days=lookback_days)).isoformat()
        for f in filings:
            if f["filingDate"] < cutoff:
                continue
            known = (today - date.fromisoformat(f["filingDate"])).days > known_after_days
            if f["form"] in ("8-K", "8-K/A"):
                for item in [i.strip() for i in f["items"].split(",") if i.strip()]:
                    if item in ITEM_FLAGS:
                        cat, title, sev, structural = ITEM_FLAGS[item]
                        flags.append(Flag(f["filingDate"], cat, title, "מאומת", sev, _impact(cat), f"{SEC} · {f['form']}",
                                          f["url"], known, structural))
            elif f["form"] in FORM_FLAGS:
                cat, title, sev = FORM_FLAGS[f["form"]]
                flags.append(Flag(f["filingDate"], cat, title, "מאומת", sev, _impact(cat), f"{SEC} · {f['form']}", f["url"], known))
        return flags

    @staticmethod
    def dilution_filings(filings: list[dict], today: date, lookback_days: int = 3 * 365) -> dict[str, Any]:
        cutoff = (today - timedelta(days=lookback_days)).isoformat()
        shelves = [f for f in filings if f["form"] in SHELF_FORMS and f["filingDate"] >= cutoff]
        offers = [f for f in filings if f["form"] in OFFERING_FORMS and f["filingDate"] >= (today - timedelta(days=365)).isoformat()]
        return {
            "shelf_filings": [{"date": f["filingDate"], "form": f["form"], "url": f["url"]} for f in shelves],
            "offering_filings": [{"date": f["filingDate"], "form": f["form"], "url": f["url"]} for f in offers],
            "has_shelf": bool(shelves),
            "has_recent_offering": bool(offers),
        }

    # ------------------------------------------------------------ insiders (Form 4)
    def insider_transactions(self, cik: int, filings: list[dict], today: date, lookback_days: int = 180, max_docs: int = 40) -> list[InsiderTx]:
        cutoff = (today - timedelta(days=lookback_days)).isoformat()
        docs = [f for f in filings if f["form"] in FORM4 and f["filingDate"] >= cutoff][:max_docs]
        out: list[InsiderTx] = []
        for f in docs:
            raw_doc = re.sub(r"^xsl[^/]+/", "", f["doc"])  # strip XSL rendering folder → raw XML
            if not raw_doc.endswith(".xml"):
                continue
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['accession'].replace('-', '')}/{raw_doc}"
            try:
                b = self.http.get_bytes(url, ttl_h=self.ttl["form4"])
            except Exception:
                continue
            if b:
                out.extend(parse_form4(b, url))
        return out


def _impact(cat: str) -> str:
    return {
        "Bankruptcy": "סיכון קיומי לבעלי המניות.",
        "Debt Acceleration": "חוב עלול להיות מיידי לפירעון — סיכון נזילות חמור.",
        "Delisting Notice": "סיכון למחיקה מהמסחר; פוגע בנזילות המניה.",
        "Accounting Issues": "דוחות קודמים אינם אמינים — פגיעה ישירה באיכות כל הנתונים הפיננסיים.",
        "Auditor Change": "יש לבדוק במסמך אם היו מחלוקות עם המבקר; התפטרות היא דגל אדום משמעותי.",
        "Cybersecurity Incident": "עלויות, תביעות ופגיעה באמון לקוחות.",
        "Impairment": "מחיקת נכסים — עשויה להעיד על כישלון השקעה או רכישה.",
        "Executive Departure": "סיכון ביצוע; יש לבדוק אם העזיבה מתוכננת.",
        "Restructuring": "עשוי לשפר מרווחים, אך מעיד על לחץ עסקי.",
        "Customer/Contract Loss": "עשוי להעיד על אובדן לקוח או שותף — לבדוק את המסמך.",
        "Share Dilution": "הנפקת מניות — דילול לבעלי המניות הקיימים.",
        "Late Filing": "איחור בדיווח מעיד לעיתים על בעיות חשבונאיות.",
        "Activist / Control": "בעל מניות אקטיביסטי — עשוי להיות קטליזטור חיובי או שלילי.",
    }.get(cat, "יש לעיין במסמך המקור.")


def _txt(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    x = el.find(path)
    if x is None:
        return None
    v = x.find("value")
    t = (v.text if v is not None else x.text) or ""
    return t.strip() or None


def parse_form4(xml_bytes: bytes, url: str) -> list[InsiderTx]:
    """Parse SEC Form 4 XML (ownershipDocument) into transactions."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    owner = root.find("reportingOwner")
    name = _txt(owner, "reportingOwnerId/rptOwnerName") or "?"
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    roles = []
    if rel is not None:
        if (_txt(rel, "isDirector") or "").lower() in ("1", "true"):
            roles.append("Director")
        if (_txt(rel, "isOfficer") or "").lower() in ("1", "true"):
            roles.append(_txt(rel, "officerTitle") or "Officer")
        if (_txt(rel, "isTenPercentOwner") or "").lower() in ("1", "true"):
            roles.append("10% Owner")
    role = ", ".join(roles) or "Other"
    plan_flag = (_txt(root, "aff10b5One") or "").lower() in ("1", "true")
    footnotes = " ".join((fn.text or "") for fn in root.iter("footnote")).lower()
    footnote_plan = "10b5-1" in footnotes
    out: list[InsiderTx] = []
    for tx in root.iter("nonDerivativeTransaction"):
        code = _txt(tx, "transactionCoding/transactionCode") or ""
        d = _txt(tx, "transactionDate") or ""
        shares = _float(_txt(tx, "transactionAmounts/transactionShares"))
        price = _float(_txt(tx, "transactionAmounts/transactionPricePerShare"))
        kind = TX_CODES.get(code, "other")
        if code == "F":
            plan = "tax"
        elif code == "S" and (plan_flag or footnote_plan):
            plan = "10b5-1"
        elif code in ("S", "P"):
            plan = "open"
        else:
            plan = "unknown"
        val = shares * price if shares is not None and price is not None else None
        out.append(InsiderTx(d[:10], name, role, code, kind, shares, price, val, plan, f"{SEC} · Form 4", url))
    return out


def _float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None
