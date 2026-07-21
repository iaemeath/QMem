"""QMem DB 状态检查脚本。用法：python check_db.py
V4.1：core_memory.db 在 mcp/qmem/ 下；project_refs 表已删；tier/origin_project 列已删（V4.1）。"""
import sqlite3, json, os

# 定位真实记忆库：tools/ 上一级 mcp/，再进 qmem/core_memory.db
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_MCP_DIR = os.path.dirname(_TOOLS_DIR)
_DBPATH = os.path.join(_MCP_DIR, 'qmem', 'core_memory.db')

try:
    conn = sqlite3.connect(_DBPATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 总量
    total = cur.execute('SELECT COUNT(*) FROM memory_facts WHERE deleted_at IS NULL').fetchone()[0]
    # 列检查（V4.1：tier/origin_project 应已不存在）
    cols = [r[1] for r in cur.execute('PRAGMA table_info(memory_facts)').fetchall()]
    # project_refs 表 V4.0 已删，存在性核对（应为 absent）
    has_refs_table = cur.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='project_refs'"
    ).fetchone()[0] > 0

    result = {
        'version': '4.1',
        'db_path': _DBPATH,
        'total_facts': total,
        'project_refs_table_exists': has_refs_table,
        'has_origin_project_column': 'origin_project' in cols,  # V4.1 应为 False
        'has_tier_column': 'tier' in cols,                      # V4.1 应为 False
    }

    # project 分布
    projects = cur.execute(
        'SELECT project, COUNT(*) n FROM memory_facts WHERE deleted_at IS NULL GROUP BY project ORDER BY n DESC'
    ).fetchall()
    result['projects'] = [dict(r) for r in projects]

    print(json.dumps(result, indent=2, ensure_ascii=False))
except Exception as e:
    print('Failed:', str(e))
