-- ============================================================
-- ТАБЛИЦЯ ПРОДАЖІВ
-- ============================================================

CREATE TABLE IF NOT EXISTS sales_history (
    id          BIGSERIAL PRIMARY KEY,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sale_date   DATE NOT NULL,
    quantity    INT NOT NULL DEFAULT 1,
    unit_price  NUMERIC(12,2) NOT NULL,
    CONSTRAINT sales_positive CHECK (quantity > 0)
);

CREATE INDEX idx_sales_product_date ON sales_history (product_id, sale_date);
CREATE INDEX idx_sales_date ON sales_history (sale_date);


-- ============================================================
-- ГЕНЕРАЦІЯ ПРОДАЖІВ ЗА 1 РІК
-- Сезонність: весна (бер-кві) та осінь (жов-лис) — пік,
--             зима (гру-лют) — мінімум
-- ============================================================

INSERT INTO sales_history (product_id, sale_date, quantity, unit_price)
WITH
dates AS (
    SELECT d::date AS sale_date
    FROM generate_series(
        CURRENT_DATE - INTERVAL '365 days',
        CURRENT_DATE - INTERVAL '1 day',
        '1 day'
    ) d
),
prods AS (
    SELECT
        p.id            AS product_id,
        s.price         AS unit_price,
        c.slug          AS category
    FROM products p
    JOIN product_stock s ON s.product_id = p.id
    LEFT JOIN categories c ON c.id = p.category_id
    WHERE p.is_active = true
),
crosses AS (
    SELECT p.product_id, p.unit_price, p.category, d.sale_date
    FROM prods p CROSS JOIN dates d
),
with_factors AS (
    SELECT
        product_id,
        sale_date,
        unit_price,
        -- Базовий денний попит за категорією (одиниць/день)
        CASE category
            WHEN 'гальма'     THEN 0.95
            WHEN 'ходова'     THEN 0.85
            WHEN 'підвіска'   THEN 0.65
            WHEN 'трансмісія' THEN 0.40
            WHEN 'двигун'     THEN 0.42
            ELSE 0.50
        END AS base_demand,
        -- Сезонний множник (Україна: ремонти навесні та перед зимою)
        CASE EXTRACT(MONTH FROM sale_date)
            WHEN 1  THEN 0.68
            WHEN 2  THEN 0.72
            WHEN 3  THEN 1.32
            WHEN 4  THEN 1.55
            WHEN 5  THEN 1.42
            WHEN 6  THEN 1.18
            WHEN 7  THEN 1.08
            WHEN 8  THEN 1.14
            WHEN 9  THEN 1.28
            WHEN 10 THEN 1.52
            WHEN 11 THEN 1.38
            WHEN 12 THEN 0.88
        END AS seasonal,
        -- Тижневий множник (субота — пік, неділя — мінімум)
        CASE EXTRACT(DOW FROM sale_date)
            WHEN 0 THEN 0.38
            WHEN 6 THEN 1.42
            ELSE 1.00
        END AS dow_factor,
        -- Детермінований шум [0.30 .. 1.60]
        0.30 + (
            ('x' || left(md5(product_id::text || '|' || sale_date::text), 8))::bit(32)::bigint % 1000
        )::numeric / 1000.0 * 1.30 AS noise
    FROM crosses
),
with_qty AS (
    SELECT
        product_id,
        sale_date,
        unit_price,
        GREATEST(0, ROUND(base_demand * seasonal * dow_factor * noise)::int) AS quantity
    FROM with_factors
)
SELECT product_id, sale_date, quantity, unit_price
FROM with_qty
WHERE quantity > 0;


-- ============================================================
-- ОНОВЛЕННЯ ЗАЛИШКІВ: поточний склад = запас на ~30 днів
-- (на базі середньоденного продажу за увесь рік)
-- ============================================================

UPDATE product_stock ps
SET quantity = GREATEST(3,
    COALESCE(
        (
            SELECT ROUND(SUM(sh.quantity)::numeric / 365.0 * 30)::int
            FROM sales_history sh
            WHERE sh.product_id = ps.product_id
        ),
        ps.quantity
    )
);
