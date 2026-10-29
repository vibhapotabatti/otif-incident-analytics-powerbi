# DAX measures

## Project 2 · OTIF (source: SQL view core.vw_order_otif, plus fact_incidents and dim_date)

```DAX
Orders Measured = CALCULATE ( COUNTROWS ( vw_order_otif ), vw_order_otif[pod_missing] = 0 )
OTIF % = DIVIDE ( CALCULATE ( COUNTROWS ( vw_order_otif ), vw_order_otif[otif] = 1 ), [Orders Measured] )
On Time % = DIVIDE ( CALCULATE ( COUNTROWS ( vw_order_otif ), vw_order_otif[on_time] = 1 ), [Orders Measured] )
In Full % = DIVIDE ( CALCULATE ( COUNTROWS ( vw_order_otif ), vw_order_otif[in_full] = 1 ), [Orders Measured] )
OTIF Gap to Target = [OTIF %] - MAX ( vw_order_otif[otif_target] )
RAG =
    SWITCH ( TRUE (),
        [OTIF %] >= 0.95, "Green",
        [OTIF %] >= 0.85, "Amber",
        "Red" )
OTIF % MoM Change = [OTIF %] - CALCULATE ( [OTIF %], DATEADD ( dim_date[date], -1, MONTH ) )

Late Orders = CALCULATE ( COUNTROWS ( vw_order_otif ), vw_order_otif[on_time] = 0 )
Incident-Linked Share of Late =
    DIVIDE ( CALCULATE ( [Late Orders], vw_order_otif[incident_linked] = 1 ), [Late Orders] )
OTIF % With Incident = CALCULATE ( [OTIF %], vw_order_otif[incident_linked] = 1 )
OTIF % No Incident = CALCULATE ( [OTIF %], vw_order_otif[incident_linked] = 0 )
Median Hours to Resolve =
    MEDIANX ( fact_incidents, DATEDIFF ( fact_incidents[opened_at], fact_incidents[resolved_at], MINUTE ) / 60 )
```

## Build checklist in Power BI Desktop
1. Get Data: SQL Server (Project 2 view) or Parquet / Databricks (Project 1 gold tables).
2. Build a dim_date table (`CALENDARAUTO()`), mark it as the date table, relate it to every fact.
3. Model view: star schema, single-direction relationships from dims to facts.
4. Add the measures above in a dedicated `_Measures` table.
5. Pages: copy the layout of supply-chain-dashboard.html (KPI cards, line chart, table with conditional formatting, bar charts).
6. Add slicers (category, DC, customer, plant, date), a drill-through page per SKU, and tooltips.
7. Row-level security: a role filtering dim_dc[region] or dim_customer to show you know RLS.
8. Publish to the Power BI Service (free trial or a Fabric trial), set scheduled refresh, add a subscription or Power Automate alert.
