"""Parity cases for the TS port of parse_form4 (Form 4 ownershipDocument XML → insider transactions).
Usage: python tests/gen_form4_parity.py <out.json>   (names, numbers and dates are arbitrary test inputs, not real filings)"""
import json, sys
from dataclasses import asdict
sys.path.insert(0, '.')
from evi.providers.edgar import parse_form4

def tx(code, d, shares, price, deriv=False, ad="D"):
    tag = "derivativeTransaction" if deriv else "nonDerivativeTransaction"
    p = "" if price is None else f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare>"
    s = "" if shares is None else f"<transactionShares><value>{shares}</value></transactionShares>"
    return (f"<{tag}><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>{d}</value></transactionDate>"
            f"<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>"
            f"<transactionAmounts>{s}{p}<transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts></{tag}>")

def doc(owner, rel, txs, aff=None, footnotes=(), decl=True):
    a = "" if aff is None else f"<aff10b5One>{aff}</aff10b5One>"
    fn = "" if not footnotes else "<footnotes>" + "".join(f'<footnote id="F{i+1}">{t}</footnote>' for i, t in enumerate(footnotes)) + "</footnotes>"
    head = '<?xml version="1.0"?>\n' if decl else ""
    return (f"{head}<ownershipDocument>\n  <schemaVersion>X0508</schemaVersion>\n  <documentType>4</documentType>{a}\n"
            f"  <issuer><issuerCik>0000000001</issuerCik></issuer>\n"
            f"  <reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>"
            f"<reportingOwnerRelationship>{rel}</reportingOwnerRelationship></reportingOwner>\n"
            f"  <nonDerivativeTable>{''.join(t for t in txs if 'nonDerivative' in t)}</nonDerivativeTable>\n"
            f"  <derivativeTable>{''.join(t for t in txs if 'nonDerivative' not in t)}</derivativeTable>{fn}\n</ownershipDocument>")

cases_in = {
    "officer_open_sale_and_tax": doc("Doe Jane", "<isOfficer>1</isOfficer><officerTitle>Chief Financial Officer</officerTitle>",
        [tx("S", "2026-10-01", 1000, 210.55), tx("F", "2026-10-02", 350, 211), tx("M", "2026-10-02", 500, 0, deriv=True)]),
    "director_10b5_flag": doc("Roe Richard &amp; Co", "<isDirector>true</isDirector><isTenPercentOwner>1</isTenPercentOwner>",
        [tx("S", "2026-09-15-05:00", "2,500" if False else 2500, 99.1), tx("P", "2026-09-20", 100, 98)], aff="1"),
    "footnote_plan_mention": doc("Poe A", "<isOfficer>1</isOfficer>", [tx("S", "2026-08-01", 300, 50)],
        footnotes=["Sold pursuant to a Rule 10b5-1 trading plan adopted on 2026-02-01.", "Weighted average price."]),
    "missing_price_and_unknown_code": doc("Moe B", "<isDirector>0</isDirector>", [tx("G", "2026-07-07", 1000, None), tx("Z", "2026-07-08", None, 10), tx("A", "2026-07-09", 10, "")]),
    "no_relationship_no_decl": doc("Noe C", "", [tx("S", "2026-06-01", 10, 1.5)], aff="0", decl=False),
    "derivative_only": doc("Zoe D", "<isOfficer>1</isOfficer><officerTitle>CEO</officerTitle>", [tx("M", "2026-05-05", 100, 5, deriv=True)]),
    "malformed": "<ownershipDocument><reportingOwner></ownershipDocument>",
}
out = [{"name": k, "xml": x, "txs": [asdict(t) for t in parse_form4(x.encode(), f"https://x/{k}.xml")]} for k, x in cases_in.items()]
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
for c in out: print(c["name"], [(t["code"], t["kind"], t["plan"], t["value"], t["role"]) for t in c["txs"]])
