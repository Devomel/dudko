-- ============================================================
-- Схема БД автомагазину + моніторинг конкурентів
-- ============================================================

-- Розширення
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- для ILIKE-пошуку по назві


-- ============================================================
-- ДОВІДНИКИ
-- ============================================================

CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(64) UNIQUE NOT NULL,   -- 'ходова', 'гальма', 'двигун'
    name        VARCHAR(128) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE brands (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(128) UNIQUE NOT NULL,  -- 'VW', 'BMW', 'Toyota'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE car_models (
    id          SERIAL PRIMARY KEY,
    brand_id    INT NOT NULL REFERENCES brands(id) ON DELETE RESTRICT,
    name        VARCHAR(256) NOT NULL,         -- 'Golf V', 'Octavia A7'
    year_from   SMALLINT,
    year_to     SMALLINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand_id, name)
);


-- ============================================================
-- ВЛАСНИЙ КАТАЛОГ (позиції магазину)
-- ============================================================

CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    article         VARCHAR(64) UNIQUE NOT NULL,
    name            VARCHAR(512) NOT NULL,
    category_id     INT REFERENCES categories(id) ON DELETE SET NULL,
    brand_id        INT REFERENCES brands(id) ON DELETE SET NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_article     ON products (article);
CREATE INDEX idx_products_category    ON products (category_id);
CREATE INDEX idx_products_brand       ON products (brand_id);
CREATE INDEX idx_products_is_active   ON products (is_active);
CREATE INDEX idx_products_name_trgm   ON products USING gin (name gin_trgm_ops);

-- Сумісність: яка запчастина підходить до яких авто
CREATE TABLE product_compatibility (
    id              SERIAL PRIMARY KEY,
    product_id      INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    car_model_id    INT NOT NULL REFERENCES car_models(id) ON DELETE CASCADE,
    notes           VARCHAR(256),
    UNIQUE (product_id, car_model_id)
);

-- Ціна та залишок власного магазину
CREATE TABLE product_stock (
    id              SERIAL PRIMARY KEY,
    product_id      INT NOT NULL REFERENCES products(id) ON DELETE CASCADE UNIQUE,
    price           NUMERIC(12,2),
    currency        CHAR(3) NOT NULL DEFAULT 'UAH',
    quantity        INT NOT NULL DEFAULT 0,
    warehouse       VARCHAR(128),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Повна історія змін ціни та залишку
CREATE TABLE product_stock_history (
    id              BIGSERIAL PRIMARY KEY,
    product_id      INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price           NUMERIC(12,2),
    currency        CHAR(3) NOT NULL DEFAULT 'UAH',
    quantity        INT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by      VARCHAR(128)   -- ім'я/логін хто змінив (необов'язково)
);

CREATE INDEX idx_stock_history_product  ON product_stock_history (product_id, changed_at DESC);


-- ============================================================
-- КОНКУРЕНТИ / ДЖЕРЕЛА
-- ============================================================

CREATE TABLE competitor_sources (
    id              SERIAL PRIMARY KEY,
    domain          VARCHAR(256) UNIQUE NOT NULL,
    appearances     INT NOT NULL DEFAULT 0,
    hits            INT NOT NULL DEFAULT 0,
    weight          NUMERIC(5,4) GENERATED ALWAYS AS (
                        CASE WHEN appearances = 0 THEN 0.5
                             ELSE ROUND(hits::NUMERIC / appearances, 4)
                        END
                    ) STORED,
    last_seen       DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- РЕЗУЛЬТАТИ СКРАПІНГУ
-- ============================================================

CREATE TABLE scraping_sessions (
    id              BIGSERIAL PRIMARY KEY,
    article         VARCHAR(64) NOT NULL,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sources_found   INT NOT NULL DEFAULT 0,
    errors_count    INT NOT NULL DEFAULT 0,
    weighted_avg    NUMERIC(12,2),
    min_price       NUMERIC(12,2),
    max_price       NUMERIC(12,2),
    median_price    NUMERIC(12,2)
);

CREATE INDEX idx_sessions_article   ON scraping_sessions (article, scraped_at DESC);

CREATE TABLE scraping_observations (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES scraping_sessions(id) ON DELETE CASCADE,
    source_id       INT REFERENCES competitor_sources(id) ON DELETE SET NULL,
    domain          VARCHAR(256) NOT NULL,
    url             TEXT NOT NULL,
    title           VARCHAR(512),
    price           NUMERIC(12,2) NOT NULL,
    raw_price       VARCHAR(64),
    currency        CHAR(3) NOT NULL DEFAULT 'UAH',
    in_stock        BOOLEAN,
    confidence      NUMERIC(4,3),   -- 0.95 / 0.85 / ...
    source_weight   NUMERIC(4,3),
    effective_weight NUMERIC(4,3),
    parser_source   VARCHAR(32),    -- 'json-ld', 'microdata', 'css'
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_obs_session    ON scraping_observations (session_id);
CREATE INDEX idx_obs_domain     ON scraping_observations (domain);
CREATE INDEX idx_obs_price      ON scraping_observations (price);


-- ============================================================
-- ТРИГЕРИ — автооновлення updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_stock_updated_at
    BEFORE UPDATE ON product_stock
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON competitor_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Тригер: при зміні ціни/залишку → пишемо в product_stock_history
CREATE OR REPLACE FUNCTION log_stock_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.price IS DISTINCT FROM NEW.price OR OLD.quantity IS DISTINCT FROM NEW.quantity) THEN
        INSERT INTO product_stock_history (product_id, price, currency, quantity)
        VALUES (NEW.product_id, NEW.price, NEW.currency, NEW.quantity);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_log_stock_change
    AFTER UPDATE ON product_stock
    FOR EACH ROW EXECUTE FUNCTION log_stock_change();

-- Тригер: при INSERT в product_stock — також пишемо початковий запис в history
CREATE OR REPLACE FUNCTION log_stock_insert()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO product_stock_history (product_id, price, currency, quantity)
    VALUES (NEW.product_id, NEW.price, NEW.currency, NEW.quantity);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_log_stock_insert
    AFTER INSERT ON product_stock
    FOR EACH ROW EXECUTE FUNCTION log_stock_insert();


-- ============================================================
-- В'ЮХИ (VIEWS) для зручних запитів
-- ============================================================

-- Повна картка позиції магазину
CREATE VIEW v_products AS
SELECT
    p.id,
    p.article,
    p.name,
    p.description,
    p.is_active,
    c.slug   AS category,
    b.name   AS brand,
    s.price,
    s.currency,
    s.quantity,
    s.warehouse,
    p.created_at,
    p.updated_at
FROM products p
LEFT JOIN categories    c ON c.id = p.category_id
LEFT JOIN brands        b ON b.id = p.brand_id
LEFT JOIN product_stock s ON s.product_id = p.id;

-- Остання ціна кожного конкурента по артикулу
CREATE VIEW v_competitor_prices AS
SELECT DISTINCT ON (o.domain, s.article)
    s.article,
    o.domain,
    o.price,
    o.currency,
    o.in_stock,
    o.effective_weight,
    o.parser_source,
    o.url,
    s.scraped_at
FROM scraping_observations o
JOIN scraping_sessions s ON s.id = o.session_id
ORDER BY o.domain, s.article, s.scraped_at DESC;

-- Зведення по артикулу: наша ціна vs ринок
CREATE VIEW v_price_comparison AS
SELECT
    p.article,
    p.name,
    s.price                     AS our_price,
    s.currency,
    mkt.min_price               AS market_min,
    mkt.max_price               AS market_max,
    mkt.weighted_avg            AS market_avg,
    CASE
        WHEN s.price IS NULL OR mkt.min_price IS NULL THEN NULL
        WHEN s.price <= mkt.min_price THEN 'lowest'
        WHEN s.price <= mkt.weighted_avg THEN 'competitive'
        ELSE 'above_market'
    END                         AS price_position,
    mkt.last_scraped_at
FROM products p
LEFT JOIN product_stock s ON s.product_id = p.id
LEFT JOIN (
    SELECT
        article,
        MIN(min_price)    AS min_price,
        MAX(max_price)    AS max_price,
        AVG(weighted_avg) AS weighted_avg,
        MAX(scraped_at)   AS last_scraped_at
    FROM scraping_sessions
    WHERE scraped_at > now() - INTERVAL '7 days'
    GROUP BY article
) mkt ON mkt.article = p.article;


-- ============================================================
-- ФУНКЦІЇ CRUD ДЛЯ ПОЗИЦІЙ
-- ============================================================

-- Додати або оновити позицію (upsert)
CREATE OR REPLACE FUNCTION upsert_product(
    p_article       VARCHAR,
    p_name          VARCHAR,
    p_category_slug VARCHAR DEFAULT NULL,
    p_brand_name    VARCHAR DEFAULT NULL,
    p_description   TEXT    DEFAULT NULL
) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_category_id INT;
    v_brand_id    INT;
    v_product_id  INT;
BEGIN
    IF p_category_slug IS NOT NULL THEN
        INSERT INTO categories (slug, name) VALUES (p_category_slug, p_category_slug)
        ON CONFLICT (slug) DO NOTHING;
        SELECT id INTO v_category_id FROM categories WHERE slug = p_category_slug;
    END IF;

    IF p_brand_name IS NOT NULL THEN
        INSERT INTO brands (name) VALUES (p_brand_name)
        ON CONFLICT (name) DO NOTHING;
        SELECT id INTO v_brand_id FROM brands WHERE name = p_brand_name;
    END IF;

    INSERT INTO products (article, name, category_id, brand_id, description)
    VALUES (p_article, p_name, v_category_id, v_brand_id, p_description)
    ON CONFLICT (article) DO UPDATE SET
        name        = EXCLUDED.name,
        category_id = COALESCE(EXCLUDED.category_id, products.category_id),
        brand_id    = COALESCE(EXCLUDED.brand_id, products.brand_id),
        description = COALESCE(EXCLUDED.description, products.description)
    RETURNING id INTO v_product_id;

    RETURN v_product_id;
END;
$$;

-- Оновити ціну та залишок
CREATE OR REPLACE FUNCTION set_stock(
    p_article   VARCHAR,
    p_price     NUMERIC,
    p_quantity  INT,
    p_currency  CHAR(3)     DEFAULT 'UAH',
    p_warehouse VARCHAR     DEFAULT NULL,
    p_changed_by VARCHAR    DEFAULT NULL
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_product_id INT;
BEGIN
    SELECT id INTO v_product_id FROM products WHERE article = p_article;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product with article % not found', p_article;
    END IF;

    INSERT INTO product_stock (product_id, price, currency, quantity, warehouse)
    VALUES (v_product_id, p_price, p_currency, p_quantity, p_warehouse)
    ON CONFLICT (product_id) DO UPDATE SET
        price     = EXCLUDED.price,
        currency  = EXCLUDED.currency,
        quantity  = EXCLUDED.quantity,
        warehouse = COALESCE(EXCLUDED.warehouse, product_stock.warehouse);
END;
$$;

-- М'яке видалення (деактивація) позиції
CREATE OR REPLACE FUNCTION deactivate_product(p_article VARCHAR)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    UPDATE products SET is_active = false WHERE article = p_article;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product with article % not found', p_article;
    END IF;
END;
$$;

-- Повне видалення позиції (каскадно)
CREATE OR REPLACE FUNCTION delete_product(p_article VARCHAR)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM products WHERE article = p_article;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product with article % not found', p_article;
    END IF;
END;
$$;

-- Пошук позицій (по артикулу або назві)
CREATE OR REPLACE FUNCTION search_products(p_query VARCHAR)
RETURNS TABLE (
    id          INT,
    article     VARCHAR,
    name        VARCHAR,
    category    VARCHAR,
    brand       VARCHAR,
    price       NUMERIC,
    quantity    INT,
    is_active   BOOLEAN
) LANGUAGE sql STABLE AS $$
    SELECT
        p.id, p.article, p.name,
        c.slug, b.name,
        s.price, s.quantity,
        p.is_active
    FROM products p
    LEFT JOIN categories    c ON c.id = p.category_id
    LEFT JOIN brands        b ON b.id = p.brand_id
    LEFT JOIN product_stock s ON s.product_id = p.id
    WHERE
        p.article ILIKE '%' || p_query || '%'
        OR p.name ILIKE '%' || p_query || '%'
    ORDER BY p.is_active DESC, p.article;
$$;


-- ============================================================
-- ПОЧАТКОВІ ДАНІ (довідники)
-- ============================================================

INSERT INTO categories (slug, name) VALUES
    ('ходова',    'Ходова частина'),
    ('гальма',    'Гальмівна система'),
    ('двигун',    'Двигун'),
    ('підвіска',  'Підвіска'),
    ('кузов',     'Кузов'),
    ('електрика', 'Електрика'),
    ('трансмісія','Трансмісія'),
    ('охолодження','Система охолодження'),
    ('мастила',   'Мастила та рідини'),
    ('інше',      'Інше')
ON CONFLICT (slug) DO NOTHING;
