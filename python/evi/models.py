"""Core data types.

Every number in the system is wrapped in `Val`, which carries provenance:
  layer  — RAW (from a provider), CALC (deterministic calculation), MODEL (model estimate), AI (interpretation)
  source — where it came from (provider + endpoint/tag)
  as_of  — the date the value describes (period end / quote time)
  fetched — when it was retrieved
A missing value is `Val(None, ...)` with a `note` saying why. Nothing is ever back-filled with demo data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

LAYERS = ("RAW", "CALC", "MODEL", "AI")


@dataclass
class Val:
    value: Any = None
    source: str = ""
    as_of: str | None = None
    layer: str = "RAW"
    note: str = ""
    fetched: str | None = None
    url: str | None = None

    @property
    def ok(self) -> bool:
        v = self.value
        if v is None:
            return False
        if isinstance(v, float) and (v != v):  # NaN
            return False
        return True

    def __bool__(self) -> bool:  # truthiness = availability
        return self.ok


def missing(why: str, source: str = "") -> Val:
    return Val(None, source=source, note=why)


def v(x: Val | None) -> Any:
    """Return raw value or None."""
    return x.value if isinstance(x, Val) and x.ok else None


def calc(value: Any, source: str, inputs: Iterable[Val] = (), note: str = "") -> Val:
    """A CALC-layer value. as_of = oldest as_of of inputs (conservative)."""
    dates = [i.as_of for i in inputs if isinstance(i, Val) and i.as_of]
    as_of = min(dates) if dates else None
    if value is None:
        miss = [i.note or i.source for i in inputs if isinstance(i, Val) and not i.ok]
        return Val(None, source=source, as_of=as_of, layer="CALC", note=note or ("חסר קלט: " + "; ".join(m for m in miss if m)))
    return Val(value, source=source, as_of=as_of, layer="CALC", note=note)


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


@dataclass
class Flag:
    date: str
    category: str
    title: str
    status: str  # 'מאומת' (official filing) | 'דיווח תקשורתי' | 'ספקולטיבי'
    severity: int  # 1..4
    impact: str
    source: str
    url: str | None = None
    known: bool = True  # older than N days → assumed known to market
    structural: bool = False


@dataclass
class InsiderTx:
    date: str
    who: str
    role: str
    code: str  # Form 4 transaction code
    kind: str  # 'sell' | 'buy' | 'tax' | 'other'
    shares: float | None
    price: float | None
    value: float | None  # USD
    plan: str  # '10b5-1' | 'tax' | 'open' | 'unknown'
    source: str
    url: str | None = None


@dataclass
class CompanyData:
    ticker: str
    cik: int | None
    name: str
    exchange: str | None
    sector: str | None
    sic: str | None = None
    sic_desc: str | None = None
    fin: dict[str, Val] = field(default_factory=dict)          # latest / TTM fundamentals
    annual: dict[str, list[dict]] = field(default_factory=dict)  # field -> [{end,val,start,tag}]
    quarterly: dict[str, list[dict]] = field(default_factory=dict)
    maturities: list[dict] = field(default_factory=list)
    maturities_as_of: str | None = None
    price: Val = field(default_factory=lambda: missing("אין ספק מחיר מוגדר"))
    prices: Any = None  # pandas DataFrame (date index; open/high/low/close/volume) or None
    prices_source: str | None = None
    quote_meta: dict[str, Val] = field(default_factory=dict)  # 52w high/low, returns (Finnhub metric)
    next_earnings: dict[str, Any] = field(default_factory=dict)
    surprises: list[dict] = field(default_factory=list)
    surprises_source: str | None = None
    earnings_events: list[dict] = field(default_factory=list)  # 8-K Item 2.02: {accepted, filed, url}
    flags: list[Flag] = field(default_factory=list)
    insiders: list[InsiderTx] = field(default_factory=list)
    dilution: dict[str, Any] = field(default_factory=dict)
    recommendations: list[dict] = field(default_factory=list)
    estimate_history: list[dict] = field(default_factory=list)  # local snapshots of consensus
    manual: dict[str, Any] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)  # human-readable list of missing inputs
    sources_used: dict[str, str] = field(default_factory=dict)  # data group -> source + fetched time
    errors: list[str] = field(default_factory=list)

    def f(self, key: str) -> Val:
        val = self.fin.get(key)
        return val if val is not None else missing("לא נמצא בדיווחי XBRL")
