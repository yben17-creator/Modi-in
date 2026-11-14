"""Sector classification.

SEC SIC codes are coarse (no 'Cybersecurity' or 'AI' code), so classification is:
  1) manual override from data/sector_overrides.csv (ticker,sector) — editable by the user
  2) SIC code mapping below
  3) otherwise None (not in the tech universe)
The UI always shows which method was used.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .config import ROOT

SECTORS = ["Software & SaaS", "Artificial Intelligence", "Cloud Computing", "Cybersecurity", "Enterprise Technology",
           "Semiconductors", "Data Infrastructure", "Automation & Robotics"]

SIC_MAP: dict[str, str] = {
    "7372": "Software & SaaS",            # Prepackaged software
    "7371": "Enterprise Technology",      # Computer programming services
    "7373": "Enterprise Technology",      # Computer integrated systems design
    "7374": "Cloud Computing",            # Computer processing & data preparation
    "7370": "Cloud Computing",            # Computer programming, data processing
    "7379": "Enterprise Technology",      # Computer related services NEC
    "7377": "Enterprise Technology",
    "3674": "Semiconductors",             # Semiconductors & related devices
    "3672": "Semiconductors",             # Printed circuit boards
    "3559": "Semiconductors",             # Special industry machinery (incl. semi equipment) — approximate
    "3825": "Semiconductors",             # Instruments for measuring electricity (incl. semi test) — approximate
    "3576": "Enterprise Technology",      # Computer communications equipment
    "3570": "Enterprise Technology", "3571": "Enterprise Technology", "3572": "Enterprise Technology",
    "3575": "Enterprise Technology", "3577": "Enterprise Technology", "3578": "Enterprise Technology",
    "3661": "Enterprise Technology", "3663": "Enterprise Technology", "3669": "Enterprise Technology",
    "3569": "Automation & Robotics",      # General industrial machinery NEC
    "3823": "Automation & Robotics",      # Industrial instruments for measurement & control
    "3829": "Automation & Robotics",
    "3560": "Automation & Robotics", "3561": "Automation & Robotics", "3562": "Automation & Robotics",
    "3565": "Automation & Robotics", "3537": "Automation & Robotics",
}

_OVR: dict[str, str] | None = None


def overrides(path: Path | None = None) -> dict[str, str]:
    global _OVR
    if _OVR is None:
        p = path or ROOT / "data" / "sector_overrides.csv"
        _OVR = {}
        if p.exists():
            with p.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if row.get("ticker") and row.get("sector") in SECTORS:
                        _OVR[row["ticker"].strip().upper()] = row["sector"]
    return _OVR


def classify(ticker: str, sic: str | None) -> tuple[str | None, str]:
    o = overrides().get(ticker.upper())
    if o:
        return o, "קובץ סיווג ידני (sector_overrides.csv)"
    if sic and str(sic) in SIC_MAP:
        return SIC_MAP[str(sic)], f"קוד SIC {sic} (SEC)"
    return None, f"קוד SIC {sic or '—'} מחוץ לסקטורים הנסרקים"
