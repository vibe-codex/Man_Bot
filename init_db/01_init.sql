-- Включение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Основная таблица знаний
CREATE TABLE IF NOT EXISTS knowledge_units (
    id SERIAL PRIMARY KEY,
    ku_id TEXT UNIQUE,
    title TEXT,
    content TEXT,
    yaml JSONB,
    level TEXT,
    user_level_fit TEXT[],
    stage TEXT[],
    channel TEXT[],
    goal TEXT[],
    style TEXT[],
    riskiness INT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    embedding VECTOR(768)
);

-- Индексы для фильтрации
CREATE INDEX IF NOT EXISTS idx_ku_level ON knowledge_units(level);
CREATE INDEX IF NOT EXISTS idx_ku_stage ON knowledge_units USING GIN(stage);
CREATE INDEX IF NOT EXISTS idx_ku_channel ON knowledge_units USING GIN(channel);
CREATE INDEX IF NOT EXISTS idx_ku_goal ON knowledge_units USING GIN(goal);
CREATE INDEX IF NOT EXISTS idx_ku_style ON knowledge_units USING GIN(style);

-- Векторный индекс (для быстрого поиска похожих)
CREATE INDEX IF NOT EXISTS idx_ku_embedding ON knowledge_units 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Истории учеников
CREATE TABLE IF NOT EXISTS student_stories (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT,
    level TEXT,
    stage TEXT[],
    channel TEXT[],
    goal TEXT[],
    text TEXT,
    outcome TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_stories_user ON student_stories(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_stories_outcome ON student_stories(outcome);
CREATE INDEX IF NOT EXISTS idx_stories_processed ON student_stories(processed);

-- Таблица пользователей бота
CREATE TABLE IF NOT EXISTS bot_users (
    telegram_user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    level TEXT DEFAULT 'новичок',
    mode TEXT DEFAULT 'field',
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

-- Таблица диалогов
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT REFERENCES bot_users(telegram_user_id),
    message TEXT,
    response TEXT,
    used_ku_ids TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);