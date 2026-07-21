-- ============================================================
-- QMem schema v4 —— Y 方案瘦身：纯项目记忆（单 tier，无共识域）
-- ============================================================
-- V4.0 改动（2026-07-20）：
--   1. 删除 project_refs 表（瘦身后无跨项目共识引用机制）
--   2. 删除 idx_facts_tier / idx_facts_origin 索引（单 tier 后无意义）
--   3. 业务概念已迁 domain_knowledge.db（DomainKG MCP），技术规范在全局 CLAUDE.md
-- V4.1 改动（2026-07-21）：
--   4. 彻底删除 tier / origin_project 列（V4.0 保留作迁移兼容，现已确认无代码读写，删除）
-- ============================================================

-- DDL 1: 记忆事实表（V4.1：纯项目记忆，无 tier/origin_project 列）
CREATE TABLE IF NOT EXISTS memory_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_uuid TEXT UNIQUE NOT NULL,
    project TEXT NOT NULL DEFAULT '',     -- 项目名（如 changzhou-balance-plan）
    topic_key TEXT DEFAULT '',
    title TEXT DEFAULT '',
    content TEXT NOT NULL,
    type TEXT DEFAULT 'manual',           -- decision/bugfix/reference/learning/manual/progress
    content_hash TEXT DEFAULT '',         -- sha256(title+content)[:16]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- DDL 2: sqlite-vec 向量虚表（512 维 BGE-small-zh，cosine 距离）
CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
    embedding float[512] distance_metric=cosine
);

-- DDL 3: FTS5 全文索引（external-content，指向 memory_facts）
CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
    title, content, topic_key, type, project,
    content='memory_facts',
    content_rowid='id',
    tokenize='unicode61'
);

-- ============================================================
-- 触发器：memory_facts ↔ memory_vectors / memory_facts_fts 同步
-- ============================================================

CREATE TRIGGER IF NOT EXISTS trg_fts_insert
AFTER INSERT ON memory_facts
BEGIN
    INSERT INTO memory_facts_fts(rowid, title, content, topic_key, type, project)
    VALUES (new.id, new.title, new.content, new.topic_key, new.type, new.project);
END;

CREATE TRIGGER IF NOT EXISTS trg_fts_update
AFTER UPDATE ON memory_facts
BEGIN
    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, title, content, topic_key, type, project)
    VALUES ('delete', old.id, old.title, old.content, old.topic_key, old.type, old.project);
    INSERT INTO memory_facts_fts(rowid, title, content, topic_key, type, project)
    VALUES (new.id, new.title, new.content, new.topic_key, new.type, new.project);
END;

CREATE TRIGGER IF NOT EXISTS trg_fts_delete
AFTER DELETE ON memory_facts
BEGIN
    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, title, content, topic_key, type, project)
    VALUES ('delete', old.id, old.title, old.content, old.topic_key, old.type, old.project);
END;

CREATE TRIGGER IF NOT EXISTS trg_vector_delete
AFTER DELETE ON memory_facts
BEGIN
    DELETE FROM memory_vectors WHERE rowid = old.id;
END;

-- ============================================================
-- 索引（V4.0：去掉 tier/origin 索引和 project_refs 表）
-- ============================================================
-- 注：memory_facts 的 FTS5/向量同步由上方触发器维护；tier/origin_project 列已删（V4.1）
CREATE INDEX IF NOT EXISTS idx_facts_project ON memory_facts(project);
CREATE INDEX IF NOT EXISTS idx_facts_topic ON memory_facts(topic_key);
CREATE INDEX IF NOT EXISTS idx_facts_type ON memory_facts(type);
CREATE INDEX IF NOT EXISTS idx_facts_deleted ON memory_facts(deleted_at);
CREATE INDEX IF NOT EXISTS idx_facts_created ON memory_facts(created_at);
