#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域知识图谱端到端验证（独立测试库，不污染 core_memory.db）
覆盖：建表 → 写概念卡 → 强熔断 → 第二概念 → 建边 → RRF 检索 → 递归 CTE 图遍历
"""
import os
import sys
import json
import tempfile

# 切到 domain-kg 目录，保证 import embedding / kg.* 能找到
_HERE = os.path.dirname(os.path.abspath(__file__))        # domain-kg/kg/
_PYDIR = os.path.dirname(_HERE)                            # domain-kg/
sys.path.insert(0, _PYDIR)

from kg.kg_store import KGStore
from kg.kg_traversal import KGTraversal
import sqlite3


def run_schema(db_path):
    """执行 kg_schema.sql 建表"""
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(conn)
    schema_path = os.path.join(_PYDIR, "kg_schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("[1] 建表 OK")


def main():
    # 临时库
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="kg_test_")
    os.close(fd)
    print(f"测试库: {db_path}")

    run_schema(db_path)

    store = KGStore(db_path)
    traversal = KGTraversal(db_path, embedder=store.embedder)

    # [2] 写第一个概念卡：发电计划
    print("\n[2] 写概念卡：发电计划")
    r = store.save_concept(
        name="发电计划",
        definition="发电计划是发电机组在未来某时段内的出力安排，是电网调度的核心依据。",
        misconception="发电计划不是某个实体的属性字段，而是独立的核心业务概念，有日前/实时/日内等多种时序类型。",
        aliases="出力计划,计划曲线",
        source="电力调度自动化原理"
    )
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") == "created", "首次写入应为 created"
    obs1 = r["obs_id"]

    # [3a] FTS 别名熔断：写'出力计划'（已是发电计划的别名，应被拦）
    print("\n[3a] FTS 别名熔断：写'出力计划'（发电计划的别名，应被拦）")
    r = store.save_concept(name="出力计划", definition="发电机组的出力安排曲线。")
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert "warning" in r, "出力计划是发电计划别名，FTS 应拦下"
    print("  ✅ 别名熔断生效，命中:", [(c["name"], c["match"]) for c in r["candidates"]])

    # [3b] 向量字面熔断：写'发电机组出力计划'（与发电计划字面重叠 0.784>0.75，应被拦）
    print("\n[3b] 向量字面熔断：写'发电机组出力计划'（字面重叠，应被拦）")
    r = store.save_concept(name="发电机组出力计划", definition="发电机组未来某时段的出力安排。")
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert "warning" in r, "发电机组出力计划与发电计划字面重叠(0.784)，向量应拦下"
    print("  ✅ 向量熔断生效，候选:", [(c["name"], c["similarity"]) for c in r["candidates"]])

    # [4] 写第二个不同概念：可调能力
    print("\n[4] 写概念卡：可调能力")
    r = store.save_concept(
        name="可调能力",
        definition="可调能力是发电侧或负荷侧在规定时间内可提供的上调/下调容量，是电力平衡的基础。",
        misconception="可调能力不是发电计划，是计划的约束边界；发电计划受断面和可调能力共同约束。",
        aliases="调节能力,备用容量",
        source="电力市场基础"
    )
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") == "created", "可调能力应为 created"
    obs2 = r["obs_id"]

    # [5] 写第三个概念：断面（电力专业词，非地质/UI）
    print("\n[5] 写概念卡：断面")
    r = store.save_concept(
        name="断面",
        definition="电力系统的输电断面是一组潮流方向相同、电气距离相近的输电线路集合，存在传输限额约束。",
        misconception="这里的'断面'是电力输电断面，不是地质断面、不是 UI 截面、不是数据切片。",
        aliases="输电断面,潮流断面",
        source="电力系统分析【来源待核实】"
    )
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") == "created", "断面应为 created"

    # [6] 建边：断面 约束 可调能力；发电计划 依赖 可调能力
    print("\n[6] 建关系边")
    r = store.save_edge("断面", "可调能力", "constrains", note="断面限额约束可调能力的上限")
    print("  断面-constrains->可调能力:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") in ("created", "exists")

    r = store.save_edge("发电计划", "可调能力", "depends_on", note="发电计划编制依赖可调能力评估")
    print("  发电计划-depends_on->可调能力:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") in ("created", "exists")

    # [7] 建边校验：非法关系类型
    print("\n[7] 非法关系类型校验")
    r = store.save_edge("发电计划", "可调能力", "is_a")
    print("  非法关系 'is_a':", json.dumps(r, ensure_ascii=False))
    assert "error" in r, "非法关系应被拒"

    # [8] 建边校验：两端概念必须存在
    print("\n[8] 不存在的概念建边")
    r = store.save_edge("不存在的概念", "可调能力", "constrains")
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert "error" in r, "引用不存在的概念应被拒"

    # [9] RRF 检索：搜"发电"
    print("\n[9] RRF 检索：query='发电'")
    r = traversal.recall("发电", min_similarity=0.3, limit=5)
    print(f"  命中 {r['total']} 条:")
    for item in r["results"]:
        print(f"    - {item['name']} (score={item['score']}, sim={item.get('similarity')})")
    assert r["total"] >= 1, "搜'发电'至少命中发电计划"
    # 确认"出力计划"未被独立写入（要么熔断拦下，要么 force；本测试未 force，故应只有发电计划）
    names = [item["name"] for item in r["results"]]
    assert "出力计划" not in names, "出力计划应被熔断拦截，不应独立存在"

    # [10] RRF 检索：搜"调整容量"（测同义词/语义召回）
    print("\n[10] RRF 检索：query='调整容量'（测语义召回别名）")
    r = traversal.recall("调整容量", min_similarity=0.3, limit=5)
    print(f"  命中 {r['total']} 条:")
    for item in r["results"]:
        print(f"    - {item['name']} (score={item['score']}, sim={item.get('similarity')})")

    # [11] 递归 CTE 图遍历：以"发电计划"为中心
    print("\n[11] 图遍历：center='发电计划', depth=2")
    r = traversal.neighbors(name="发电计划", depth=2)
    print(f"  节点 {r['node_count']} 个, 边 {r['edge_count']} 条")
    print(f"  到达概念: {[n['name'] for n in r['nodes']]}")
    for e in r["edges"]:
        print(f"    边: {e['src_concept']} --{e['relation_type']}--> {e['dst_concept']}")
    assert r["node_count"] >= 1, "图遍历至少返回中心节点"

    # [12] 概念卡列表
    print("\n[12] 概念卡列表（待核实 verified=0）")
    lst = store.list_concepts(verified=0)
    print(f"  待核实概念 {len(lst)} 个: {[c['name'] for c in lst]}")

    # [13] update：标记发电计划已核实
    print("\n[13] concept_update：标记'发电计划' verified=1")
    r = store.update_concept(obs1, verified=1)
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert r.get("action") == "updated"

    # [14] get 单卡
    print("\n[14] concept_get：拉'发电计划'完整内容")
    c = store.get_concept(obs_id=obs1)
    print(f"  name={c['name']}, verified={c['verified']}")
    print(f"  definition={c['definition'][:40]}...")
    print(f"  misconception={c['misconception'][:40]}...")
    assert c["verified"] == 1

    # [15] 边删除
    print("\n[15] edge_delete：删 '发电计划' depends_on '可调能力'")
    r = store.delete_edge(src_concept="发电计划", dst_concept="可调能力", relation_type="depends_on")
    print("  结果:", json.dumps(r, ensure_ascii=False))
    assert r.get("affected") >= 1

    # 清理
    os.unlink(db_path)
    print(f"\n[OK] 全部通过，已清理测试库")


if __name__ == "__main__":
    main()
