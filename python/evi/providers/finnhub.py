"""Finnhub provider (optional — enabled when FINNHUB_API_KEY is set).

Free-tier endpoints used: quote, stock/metric (52w range, returns, beta), calendar/earnings (dates + consensus),
stock/earnings (last ~4 EPS surprises), stock/recommendation, company-news, stock/profile2.
Endpoints that require a paid plan return 403 — they are reported as unavailable, never substituted.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ..http import CachedHttp, HttpError
from ..models import Flag, Val, missing
from ..store import Store

BASE = "https://finnhub.io/api/v1"
SRC = "Finnhub"

NEWS_RULES: list[tuple[tuple[str, ...], str, str, int, bool]] = [
    (("short seller", "short report", "short-seller"), "Short Seller Report", "דוח Short Seller", 3, False),
    (("sec investigation", "sec probe", "doj", "subpoena", "ftc", "regulator", "antitrust"), "Regulatory", "חקירה / בירור רגולטורי", 3, False),
    (("class action", "lawsuit", "sues", "sued", "litigation"), "Litigation", "תביעה משפטית", 2, False),
    (("breach", "hack", "ransomware", "cyberattack", "outage"), "Cybersecurity Incident", "אירוע סייבר / תקלה", 2, False),
    (("restate", "accounting irregular", "material weakness"), "Accounting Issues", "סוגיה חשבונאית", 3, False),
    (("auditor resign", "auditor quits"), "Auditor Resignation", "התפטרות מבקר", 4, False),
    (("cuts guidance", "lowers guidance", "lowered guidance", "guidance cut", "slashes outlook", "cuts outlook", "lowers outlook"), "Guidance Cut", "הורדת תחזית", 3, False),
    (("ceo resign", "cfo resign", "steps down", "departure", "ousted"), "Executive Departure", "עזיבת בכיר", 2, False),
    (("loses contract", "customer loss", "terminates agreement"), "Customer Loss", "אובדן לקוח / חוזה", 2, False),
    (("recall", "product failure", "defect"), "Product Failure", "כשל מוצר", 2, False),
    (("ai disruption", "disrupted by ai", "ai threat", "competition intensif", "price war"), "Competitive Threat", "איום תחרותי", 2, True),
    (("offering", "atm program", "at-the-market"), "Share Dilution", "הנפקת מניות", 2, False),
]


class FinnhubProvider:
    name = SRC

    def __init__(self, store: Store, api_key: str, per_second: float = 0.9, ttl_h: float = 6):
        self.key = api_key
        self.http = CachedHttp(store, "finnhub", per_second)
        self.ttl = ttl_h
        self.unavailable: set[str] = set()

    def _get(self, path: str, ttl_h: float | None = None, **params: Any) -> Any:
        if path in self.unavailable:
            return None
        try:
            return self.http.get_json(f"{BASE}/{path}", {**params, "token": self.key}, ttl_h=self.ttl if ttl_h is None else ttl_h,
                                      secret=("token",))
        except HttpError as e:
            if e.status in (401, 403):
                self.unavailable.add(path)  # not in this plan
                return None
            raise

    def fetched_at(self, path: str, **params: Any) -> str | None:
        return self.http.fetched_at(f"{BASE}/{path}", params, secret=("token",))

    # ------------------------------------------------------------------
    def quote(self, symbol: str) -> Val:
        js = self._get("quote", ttl_h=0.25, symbol=symbol)
        if not js or not js.get("c"):
            return missing("Finnhub quote לא החזיר מחיר", SRC)
        ts = datetime.fromtimestamp(js["t"]).isoformat() if js.get("t") else None
        return Val(float(js["c"]), source=f"{SRC} · quote", as_of=ts, fetched=self.fetched_at("quote", symbol=symbol))

    def metrics(self, symbol: str) -> dict[str, Val]:
        js = self._get("stock/metric", symbol=symbol, metric="all")
        m = (js or {}).get("metric") or {}
        f = self.fetched_at("stock/metric", symbol=symbol, metric="all")
        def val(k: str, scale: float = 1.0) -> Val:
            x = m.get(k)
            return Val(float(x) * scale, source=f"{SRC} · stock/metric · {k}", as_of=f[:10] if f else None, fetched=f) if x is not None else missing(f"{k} לא זמין", SRC)
        return {"high52": val("52WeekHigh"), "low52": val("52WeekLow"), "ret1y": val("52WeekPriceReturnDaily", 0.01),
                "ret3m": val("13WeekPriceReturnDaily", 0.01), "beta": val("beta")}

    def earnings_calendar(self, start: date, end: date, symbol: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"from": start.isoformat(), "to": end.isoformat()}
        if symbol:
            params["symbol"] = symbol
        js = self._get("calendar/earnings", **params)
        rows = (js or {}).get("earningsCalendar") or []
        f = self.fetched_at("calendar/earnings", **params)
        return [{**r, "_source": f"{SRC} · calendar/earnings", "_fetched": f} for r in rows]

    def surprises(self, symbol: str) -> tuple[list[dict], str | None]:
        js = self._get("stock/earnings", symbol=symbol) or []
        out = []
        for r in js:
            if r.get("actual") is None or r.get("estimate") is None:
                continue
            sp = r.get("surprisePercent")
            out.append({"period": r.get("period"), "actual": r["actual"], "estimate": r["estimate"],
                        "surprise_pct": float(sp) if sp is not None else None})
        out.sort(key=lambda x: x["period"] or "")
        return out, (f"{SRC} · stock/earnings" if out else None)

    def recommendations(self, symbol: str) -> list[dict]:
        js = self._get("stock/recommendation", symbol=symbol) or []
        return sorted(js, key=lambda r: r.get("period", ""))

    def profile(self, symbol: str) -> dict:
        return self._get("stock/profile2", ttl_h=24 * 7, symbol=symbol) or {}

    def news_flags(self, symbol: str, today: date, days: int = 90, known_after_days: int = 7) -> list[Flag]:
        js = self._get("company-news", symbol=symbol, **{"from": (today - timedelta(days=days)).isoformat(), "to": today.isoformat()}) or []
        flags: list[Flag] = []
        seen: set[str] = set()
        for n in js:
            if not n.get("datetime"):
                continue  # undated item: no date to show or to judge "known to market" by
            text = f"{n.get('headline', '')} {n.get('summary', '')}".lower()
            for kws, cat, he, sev, structural in NEWS_RULES:
                if any(k in text for k in kws):
                    d = datetime.fromtimestamp(n.get("datetime", 0)).date()
                    key = f"{cat}|{d}"
                    if key in seen:
                        break
                    seen.add(key)
                    flags.append(Flag(d.isoformat(), cat, f"{he}: {n.get('headline', '')[:140]}", "דיווח תקשורתי", sev,
                                      "דיווח תקשורתי שזוהה לפי מילות מפתח — לא אומת. יש לקרוא את המקור.",
                                      f"{SRC} · company-news · {n.get('source', '')}", n.get("url"),
                                      (today - d).days > known_after_days, structural))
                    break
        return flags
