-- Project 2: OTIF + incident model (SQL Server / Azure SQL)
-- Load fact_orders.csv and fact_incidents.csv into stg.orders / stg.incidents first
-- (BULK INSERT, the Import Flat File wizard, or pandas.to_sql).

CREATE SCHEMA core;
GO
CREATE TABLE core.dim_customer (customer_key INT IDENTITY PRIMARY KEY, source_name NVARCHAR(100) UNIQUE, customer NVARCHAR(100), otif_target DECIMAL(4,3) DEFAULT 0.95);
CREATE TABLE core.fact_orders (
    order_id VARCHAR(20) PRIMARY KEY, order_date DATE, customer_key INT REFERENCES core.dim_customer,
    plant VARCHAR(30), sku_id VARCHAR(20), qty_ordered INT, qty_delivered INT,
    requested_delivery DATE, actual_delivery DATE NULL,
    on_time BIT NULL, in_full BIT, otif BIT NULL, days_late INT NULL, pod_missing BIT,
    loaded_at DATETIME2 DEFAULT SYSUTCDATETIME());
CREATE TABLE core.fact_incidents (incident_id VARCHAR(20) PRIMARY KEY, opened_at DATETIME2, resolved_at DATETIME2,
    application VARCHAR(40), priority CHAR(2), plant VARCHAR(30), category VARCHAR(40));
CREATE TABLE core.bridge_order_incident (order_id VARCHAR(20), incident_id VARCHAR(20), PRIMARY KEY (order_id, incident_id));
GO

CREATE OR ALTER PROCEDURE core.usp_load_orders AS
BEGIN
    SET NOCOUNT ON;
    -- 1. Normalise customer names through a mapping table ("TESCO LTD" -> "Tesco")
    INSERT INTO core.dim_customer (source_name, customer)
    SELECT DISTINCT s.customer,
           CASE WHEN s.customer LIKE '% LTD' THEN LEFT(s.customer, LEN(s.customer) - 4) ELSE s.customer END
    FROM stg.orders s
    WHERE NOT EXISTS (SELECT 1 FROM core.dim_customer d WHERE d.source_name = s.customer);
    -- (then fix casing once by hand in dim_customer, e.g. TESCO -> Tesco; a mapping table beats string rules)

    -- 2. Upsert orders with derived OTIF flags; missing POD scans stay NULL, not "late"
    MERGE core.fact_orders AS t
    USING (
        SELECT s.order_id, s.order_date, d.customer_key, s.plant, s.sku_id, s.qty_ordered, s.qty_delivered,
               s.requested_delivery, s.actual_delivery,
               CASE WHEN s.actual_delivery IS NULL THEN NULL WHEN s.actual_delivery <= s.requested_delivery THEN 1 ELSE 0 END AS on_time,
               CASE WHEN s.qty_delivered >= s.qty_ordered THEN 1 ELSE 0 END AS in_full,
               DATEDIFF(day, s.requested_delivery, s.actual_delivery) AS days_late,
               CASE WHEN s.actual_delivery IS NULL THEN 1 ELSE 0 END AS pod_missing
        FROM stg.orders s JOIN core.dim_customer d ON d.source_name = s.customer
    ) AS src ON t.order_id = src.order_id
    WHEN MATCHED THEN UPDATE SET actual_delivery = src.actual_delivery, qty_delivered = src.qty_delivered,
        on_time = src.on_time, in_full = src.in_full, days_late = src.days_late, pod_missing = src.pod_missing,
        otif = CASE WHEN src.on_time IS NULL THEN NULL ELSE src.on_time & src.in_full END, loaded_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (order_id, order_date, customer_key, plant, sku_id, qty_ordered, qty_delivered,
        requested_delivery, actual_delivery, on_time, in_full, otif, days_late, pod_missing)
        VALUES (src.order_id, src.order_date, src.customer_key, src.plant, src.sku_id, src.qty_ordered, src.qty_delivered,
        src.requested_delivery, src.actual_delivery, src.on_time, src.in_full,
        CASE WHEN src.on_time IS NULL THEN NULL ELSE src.on_time & src.in_full END, src.days_late, src.pod_missing);

    -- 3. Temporal range join: link orders to disruptive incidents open at the same plant (or global)
    TRUNCATE TABLE core.bridge_order_incident;
    INSERT INTO core.bridge_order_incident (order_id, incident_id)
    SELECT o.order_id, i.incident_id
    FROM core.fact_orders o
    JOIN core.fact_incidents i
      ON (i.plant = o.plant OR i.plant = 'Global')
     AND o.order_date BETWEEN CAST(i.opened_at AS DATE) AND CAST(i.resolved_at AS DATE)
    WHERE i.priority IN ('P1', 'P2')
      AND i.application IN ('SAP SD', 'EDI Gateway', 'WMS');
END;
GO

-- Reporting view: one row per order, incident link counted once
CREATE OR ALTER VIEW core.vw_order_otif AS
SELECT o.*, c.customer, c.otif_target,
       CASE WHEN EXISTS (SELECT 1 FROM core.bridge_order_incident b WHERE b.order_id = o.order_id) THEN 1 ELSE 0 END AS incident_linked,
       CASE WHEN o.pod_missing = 1 THEN 'No POD (excluded)'
            WHEN o.otif = 1 THEN 'OTIF'
            WHEN o.on_time = 0 AND EXISTS (SELECT 1 FROM core.bridge_order_incident b WHERE b.order_id = o.order_id) THEN 'Late, open incident'
            WHEN o.on_time = 0 THEN 'Late, other cause'
            ELSE 'Short shipped only' END AS failure_reason
FROM core.fact_orders o JOIN core.dim_customer c ON c.customer_key = o.customer_key;
GO

-- Sanity checks worth showing in an interview
SELECT customer, COUNT(*) AS orders, AVG(CAST(otif AS FLOAT)) AS otif_rate
FROM core.vw_order_otif WHERE pod_missing = 0 GROUP BY customer ORDER BY otif_rate;

SELECT i.application, COUNT(DISTINCT b.order_id) AS late_orders_impacted
FROM core.bridge_order_incident b
JOIN core.fact_incidents i ON i.incident_id = b.incident_id
JOIN core.fact_orders o ON o.order_id = b.order_id AND o.on_time = 0
GROUP BY i.application ORDER BY late_orders_impacted DESC;
