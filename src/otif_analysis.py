"""Clean simulated orders, link late orders to P1/P2 incidents and compute
OTIF metrics. Run after the generator: python src/otif_analysis.py
"""
import json, numpy as np, pandas as pd
from pathlib import Path

D = Path("data")

# ---------------- Project 2: OTIF + incidents ----------------
o = pd.read_csv(D / "fact_orders.csv", parse_dates=["order_date", "requested_delivery", "actual_delivery"])
inc = pd.read_csv(D / "fact_incidents.csv", parse_dates=["opened_at", "resolved_at"])
o["customer"] = o.customer.str.replace(" LTD", "", regex=False).str.title().str.replace("'S", "'s")
o["pod_missing"] = o.actual_delivery.isna()
v = o[~o.pod_missing].copy()
v["on_time"] = v.actual_delivery <= v.requested_delivery
v["in_full"] = v.qty_delivered >= v.qty_ordered
v["otif"] = v.on_time & v.in_full
dis = inc[inc.priority.isin(["P1", "P2"]) & inc.application.isin(["SAP SD", "EDI Gateway", "WMS"])]
# temporal range join (SQL equivalent: JOIN ... ON plant match AND order_date BETWEEN opened AND resolved)
links = []
for r in dis.itertuples():
    hit = v[((v.plant == r.plant) | (r.plant == "Global")) & v.order_date.between(r.opened_at.normalize(), r.resolved_at.normalize())]
    links.append(pd.DataFrame({"order_id": hit.order_id, "application": r.application}))
links = pd.concat(links).drop_duplicates("order_id")                 # count each order once
v = v.merge(links, on="order_id", how="left")
v["incident_linked"] = v.application.notna()
late = v[~v.on_time]
monthly = v.groupby(v.order_date.dt.to_period("M")).otif.mean()
cust = v.groupby("customer").otif.mean().sort_values()
app_imp = late[late.incident_linked].application.value_counts()
reasons = {
    "Late, open incident": int((~v.on_time & v.incident_linked).sum()),
    "Late, other cause": int((~v.on_time & ~v.incident_linked).sum()),
    "Short shipped only": int((v.on_time & ~v.in_full).sum()),
}
inc_day = v.groupby("incident_linked").otif.mean()
mttr = (inc.assign(h=(inc.resolved_at - inc.opened_at).dt.total_seconds() / 3600).groupby("priority").h.median())
p2 = dict(
    otif=float(v.otif.mean()), on_time=float(v.on_time.mean()), in_full=float(v.in_full.mean()),
    orders=len(o), pod_missing=int(o.pod_missing.sum()), incidents=len(inc),
    linked_share_of_late=float(late.incident_linked.mean()),
    otif_with_incident=float(inc_day[True]), otif_without_incident=float(inc_day[False]),
    monthly=[dict(m=str(k), v=round(x, 4)) for k, x in monthly.items()],
    by_customer={k: round(x, 4) for k, x in cust.items()},
    app_impact={k: int(x) for k, x in app_imp.items()},
    reasons=reasons, mttr_hours={k: round(x, 1) for k, x in mttr.items()},
)
json.dump(p2, open("dashboard_data_otif.json", "w"), indent=1)
print(json.dumps({k: v for k, v in p2.items() if not isinstance(v, (list, dict))}, indent=1))
