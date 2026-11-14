import json, math, sys, copy
sys.path.insert(0,'.')
from tests import fixtures_builder as fx
from evi.providers import xbrl
from evi.models import CompanyData, Val
from evi.analytics.metrics import compute_metrics
from evi.analytics import scores
cases=[]
def variant(name, cf, price, meta):
    x=xbrl.extract(cf)
    cd=CompanyData("TSTC",1,"T","Nasdaq","Software & SaaS")
    cd.fin,cd.annual,cd.quarterly,cd.maturities=x["fin"],x["annual"],x["quarterly"],x["maturities"]
    cd.price=Val(price,"test",'2026-11-13') if price else Val(None,note="none")
    cd.quote_meta={k:Val(v_,"test","2026-11-13") for k,v_ in meta.items()}
    cd.next_earnings={"date":"2026-11-25","source":"test","eps_est":0.9}
    m=compute_metrics(cd)
    h,sev,near=scores.health(cd,m)
    enc=lambda v: None if v is None else ("inf" if v==math.inf else "-inf" if v==-math.inf else v)
    cases.append({"name":name,"cf":cf,"price":price,"meta":meta,
      "fin":{k:enc(v.value) for k,v in x["fin"].items()},
      "metrics":{k:enc(v.value) for k,v in m.items() if k!="days_to_earnings"},
      "health":h.score,"coverage":h.coverage,"severe":sev,"near":near,"maturities":x["maturities"],
      "splits":x["splits"],"notes":{k:v.note for k,v in m.items() if k in ("cash_all","total_debt")}})
cf=fx.companyfacts(); variant("full_with_price",cf,51.2,{"high52":70,"ret3m":-0.05,"ret1y":0.1})
cf2=fx.companyfacts(); del cf2["facts"]["us-gaap"]["InterestExpense"]; del cf2["facts"]["us-gaap"]["ShortTermInvestments"]
variant("missing_tags_no_price",cf2,None,{})
cf3=fx.companyfacts(last_q_2026=1); variant("partial_year",cf3,20.0,{"high52":40})
# stock split 10:1 in mid-2024 (older dei share counts are pre-split)
cf4=fx.companyfacts()
for r in cf4["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]:
    if r["end"] < "2024-06-30": r["val"] = r["val"] / 10
variant("stock_split_10_for_1",cf4,51.2,{"high52":70})
# stale short-term investments: company stopped tagging them after 2025-03-31
cf5=fx.companyfacts()
sti=cf5["facts"]["us-gaap"]["ShortTermInvestments"]["units"]["USD"]
cf5["facts"]["us-gaap"]["ShortTermInvestments"]["units"]["USD"]=[r for r in sti if r["end"]<="2025-03-31"]
variant("stale_short_term_investments",cf5,51.2,{"high52":70})
for c in cases[3:]: print(c["name"], c["splits"], {k:c["metrics"][k] for k in ("dilution_rate","cash_all")}, c["notes"])
json.dump(cases,open(sys.argv[1],'w'))
