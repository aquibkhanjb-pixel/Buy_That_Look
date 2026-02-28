-- ================================================================
-- Fashion Recommendation System - Database Initialization
-- ================================================================
-- This script runs automatically on first PostgreSQL container start.
-- Tables are also created by SQLAlchemy's init_db(), but this ensures
-- the schema exists even before the backend boots.
-- ================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Products Table ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id VARCHAR(255) UNIQUE NOT NULL,
    source_site VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    brand VARCHAR(100),
    price NUMERIC(10, 2),
    original_price NUMERIC(10, 2),
    currency VARCHAR(3) DEFAULT 'USD',
    category VARCHAR(100),
    subcategory VARCHAR(100),
    color VARCHAR(50),
    size VARCHAR(50),
    image_url TEXT NOT NULL,
    additional_images TEXT[] DEFAULT '{}',
    product_url TEXT NOT NULL,
    embedding_id VARCHAR(255),
    faiss_index VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scraped TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_product_product_id ON products(product_id);
CREATE INDEX IF NOT EXISTS idx_product_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_product_price ON products(price);
CREATE INDEX IF NOT EXISTS idx_product_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_product_source ON products(source_site);
CREATE INDEX IF NOT EXISTS idx_product_created ON products(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_active ON products(is_active);

-- ─── Categories Table ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    level INTEGER DEFAULT 0,
    path VARCHAR(500)
);

-- ─── Embeddings Table ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE NOT NULL,
    embedding_type VARCHAR(20) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    vector_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embedding_product ON embeddings(product_id);

-- ─── Search Logs Table ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS search_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255),
    query_type VARCHAR(20) NOT NULL,
    query_text TEXT,
    query_image_hash VARCHAR(64),
    filters_applied TEXT,
    alpha_value VARCHAR(10),
    results_count INTEGER,
    top_result_ids TEXT[] DEFAULT '{}',
    latency_ms INTEGER,
    clicked_products UUID[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_session ON search_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_search_created ON search_logs(created_at DESC);

-- ─── Seed Default Categories ─────────────────────────────────────
INSERT INTO categories (name, level, path) VALUES
    ('Women', 0, 'Women'),
    ('Men', 0, 'Men'),
    ('Kids', 0, 'Kids'),
    ('Accessories', 0, 'Accessories'),
    ('Footwear', 0, 'Footwear')
ON CONFLICT (name) DO NOTHING;
