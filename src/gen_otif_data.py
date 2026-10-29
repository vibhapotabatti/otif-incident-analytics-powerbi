"""Synthetic order-fulfilment (OTIF) + application incident data (Project 2).
Orders flow through an order-management system; some delays are caused by
logged application incidents (EDI failures, interface outages), which is the
link this project analyses.
Usage: python gen_otif_data.py  -> writes CSVs to ./data/
"""
import numpy as np, pandas as pd
from pathlib import Path

rng = np.random.default_rng(7)
OUT = Path("data"); OUT.mkdir(exist_ok=True)
N_ORDERS, N_INC = 60_000, 900
customers = ["Tesco", "Sainsbury's", "Asda", "Morrisons", "Boots", "Amazon", "Ocado", "Superdrug"]
plants = ["Hull", "Derby", "Nottingham"]
start, end = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")

# --- Application incidents (ITSM-style) ---
inc_open = start + pd.to_timedelta(rng.uniform(0, (end - start).days, N_INC), unit="D")
inc = pd.DataFrame({
    "incident_id": [f"INC{700000+i}" for i in range(N_INC)],
    "opened_at": inc_open.round("min"),
    "application": rng.choice(["SAP SD", "EDI Gateway", "WMS", "TMS", "Planning Tool"], N_INC, p=[.3, .25, .2, .15, .1]),
    "priority": rng.choice(["P1", "P2", "P3", "P4"], N_INC, p=[.03, .12, .45, .40]),
    "plant": rng.choice(plants + ["Global"], N_INC),
})
hours = {"P1": 4, "P2": 12, "P3": 40, "P4": 90}
inc["resolved_at"] = inc.apply(lambda r: r.opened_at + pd.Timedelta(hours=rng.exponential(hours[r.priority])), axis=1).dt.round("min")
inc["category"] = rng.choice(["Interface failure", "Batch job failure", "Master data", "Access", "Performance"], N_INC)

# --- Orders ---
order_dt = start + pd.to_timedelta(rng.uniform(0, (end - start).days, N_ORDERS), unit="D")
orders = pd.DataFrame({
    "order_id": [f"SO{9000000+i}" for i in range(N_ORDERS)],
    "order_date": order_dt.normalize(),
    "customer": rng.choice(customers, N_ORDERS),
    "plant": rng.choice(plants, N_ORDERS),
    "sku_id": [f"SKU{1000+i}" for i in rng.integers(0, 40, N_ORDERS)],
    "qty_ordered": rng.integers(20, 800, N_ORDERS),
})
lead = orders.customer.map({"Amazon": 2, "Ocado": 2}).fillna(3)
orders["requested_delivery"] = orders.order_date + pd.to_timedelta(lead, unit="D")

# Delay drivers: base noise + active disruptive incident at the plant around order date
# tighter delivery windows (online grocers) and tougher booking rules make some customers harder to serve
late_p = orders.customer.map({"Ocado": .14, "Amazon": .12, "Tesco": .09, "Asda": .08, "Sainsbury's": .07,
                              "Morrisons": .05, "Boots": .03, "Superdrug": .04}).values
delay = np.where(rng.random(N_ORDERS) < late_p, rng.choice([1, 2], N_ORDERS, p=[.75, .25]), 0).astype(float)
disruptive = inc[inc.priority.isin(["P1", "P2"]) & inc.application.isin(["SAP SD", "EDI Gateway", "WMS"])]
for _, r in disruptive.iterrows():
    hit = (orders.plant.eq(r.plant) | (r.plant == "Global")) & orders.order_date.between(
        r.opened_at.normalize(), r.resolved_at.normalize()) & (rng.random(N_ORDERS) < 0.6)
    delay[hit.values] += rng.integers(1, 3, hit.sum())
orders["actual_delivery"] = orders.requested_delivery + pd.to_timedelta(delay, unit="D")
short = rng.random(N_ORDERS) < 0.06
orders["qty_delivered"] = np.where(short, (orders.qty_ordered * rng.uniform(.6, .95, N_ORDERS)).astype(int), orders.qty_ordered)

# Messy-source quirks
orders.loc[orders.sample(frac=.01, random_state=1).index, "actual_delivery"] = pd.NaT   # missing POD scans
orders["customer"] = orders.customer.where(rng.random(N_ORDERS) > .02, orders.customer.str.upper() + " LTD")

orders.to_csv(OUT / "fact_orders.csv", index=False)
inc.to_csv(OUT / "fact_incidents.csv", index=False)
print(len(orders), "orders,", len(inc), "incidents written to", OUT.resolve())
