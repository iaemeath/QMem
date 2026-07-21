-- ============================================================
-- 领域知识图谱 schema —— 双表（概念 + 关系）+ 向量 + FTS
-- V4.0：独立 domain_knowledge.db，与 QMem 的 core_memory.db（memory_* 表）物理隔离
-- 设计依据：update/领域知识图谱MCP-自建方案.md
-- ============================================================

-- DDL 1: 概念卡表（DCK = Domain Concept Card）
-- definition：联网搜来的权威定义（AI 填）
-- misconception：AI 易误解点（用户在 GUI 查看后补，是图谱的灵魂字段）
CREATE TABLE IF NOT EXISTS kg_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_uuid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,                 -- 概念名（唯一业务标识，如"发电计划"）
    aliases TEXT DEFAULT '',            -- 别名，逗号分隔（如"计划曲线,出力计划"），参与 FTS
    definition TEXT DEFAULT '',         -- 权威定义（联网搜来，标注来源）
    misconception TEXT DEFAULT '',      -- ⚠️ AI 易误解点（用户补充，可为空待补）
    source TEXT DEFAULT '',             -- 定义来源（URL/文献/【来源待核实】）
    verified INTEGER DEFAULT 0,         -- 0=待用户核实, 1=用户已核实（用户在 GUI 看过并确认）
    content_hash TEXT DEFAULT '',       -- sha256(name+definition+misconception+aliases)[:16]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- DDL 2: 概念向量虚表（512 维 BGE-small-zh，与 memory_vectors 同款，独立 rowid 空间）
-- rowid 与 kg_concepts.id 对齐
-- 这是【全文向量】：name+aliases+definition+misconception 拼接，用于 RRF 检索（召回优先）
CREATE VIRTUAL TABLE IF NOT EXISTS kg_vectors USING vec0(
    embedding float[512] distance_metric=cosine
);

-- DDL 2b: 概念名向量虚表（仅 name+aliases，用于强熔断）
-- 双向量设计原因：概念名是短文本（4-10字），全文向量被 definition 长文本稀释，
-- 导致同义概念名（"发电计划"vs"出力计划"）相似度被压到 0.6 以下，熔断失效。
-- name 向量只编码概念名本身，同义名相似度可达 0.8+，熔断精准。
CREATE VIRTUAL TABLE IF NOT EXISTS kg_name_vectors USING vec0(
    embedding float[512] distance_metric=cosine
);

-- DDL 3: 概念全文索引（external-content，指向 kg_concepts）
-- 索引 name/aliases/definition/misconception 四个文本字段
CREATE VIRTUAL TABLE IF NOT EXISTS kg_concepts_fts USING fts5(
    name, aliases, definition, misconception,
    content='kg_concepts',
    content_rowid='id',
    tokenize='unicode61'
);

-- DDL 4: 语义边表（6 种关系类型）
-- 关系类型约束由应用层校验（SQLite CHECK 不便扩展，且要支持未来新增关系类型）
CREATE TABLE IF NOT EXISTS kg_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src_concept TEXT NOT NULL,          -- 源概念名（kg_concepts.name）
    dst_concept TEXT NOT NULL,          -- 目标概念名（kg_concepts.name）
    relation_type TEXT NOT NULL,        -- derives_from / constrains / aggregates / depends_on / synonym_of / contradicts
    weight REAL DEFAULT 1.0,            -- 关系强度 [0,1]，默认 1.0
    note TEXT DEFAULT '',               -- 关系说明（如"发电计划约束可调能力的上限"）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(src_concept, dst_concept, relation_type)  -- 同方向同类型关系唯一，防重复边
);

-- ============================================================
-- 触发器：kg_concepts ↔ kg_concepts_fts / kg_vectors 同步
-- ============================================================

CREATE TRIGGER IF NOT EXISTS trg_kg_fts_insert
AFTER INSERT ON kg_concepts
BEGIN
    INSERT INTO kg_concepts_fts(rowid, name, aliases, definition, misconception)
    VALUES (new.id, new.name, new.aliases, new.definition, new.misconception);
END;

CREATE TRIGGER IF NOT EXISTS trg_kg_fts_update
AFTER UPDATE ON kg_concepts
BEGIN
    INSERT INTO kg_concepts_fts(kg_concepts_fts, rowid, name, aliases, definition, misconception)
    VALUES ('delete', old.id, old.name, old.aliases, old.definition, old.misconception);
    INSERT INTO kg_concepts_fts(rowid, name, aliases, definition, misconception)
    VALUES (new.id, new.name, new.aliases, new.definition, new.misconception);
END;

CREATE TRIGGER IF NOT EXISTS trg_kg_fts_delete
AFTER DELETE ON kg_concepts
BEGIN
    INSERT INTO kg_concepts_fts(kg_concepts_fts, rowid, name, aliases, definition, misconception)
    VALUES ('delete', old.id, old.name, old.aliases, old.definition, old.misconception);
END;

CREATE TRIGGER IF NOT EXISTS trg_kg_vector_delete
AFTER DELETE ON kg_concepts
BEGIN
    DELETE FROM kg_vectors WHERE rowid = old.id;
    DELETE FROM kg_name_vectors WHERE rowid = old.id;
END;

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_kg_concepts_name ON kg_concepts(name);
CREATE INDEX IF NOT EXISTS idx_kg_concepts_verified ON kg_concepts(verified);
CREATE INDEX IF NOT EXISTS idx_kg_concepts_deleted ON kg_concepts(deleted_at);
CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src_concept);
CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst_concept);
CREATE INDEX IF NOT EXISTS idx_kg_edges_type ON kg_edges(relation_type);
