#!/usr/bin/env python3
# ============================================================================
# SoulMem — SOP Funnel
# Connects SOP operations to the funnel system
# When SOP is used or created, auto-write to SoulMem via funnel
# ============================================================================

import os
import sys
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH


class SOPFunnel:
    """SOP → Funnel → SoulMem"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def on_sop_used(self, slug: str, success: bool = True, notes: str = ""):
        """
        SOP 被使用时，自动写入 SoulMem
        
        Args:
            slug: SOP 标识符
            success: 是否成功
            notes: 使用备注
        """
        from sop_manager import SOPManager
        manager = SOPManager()
        sop = manager.get_sop(slug)
        
        if not sop:
            return None
        
        # 更新使用记录
        manager.record_usage(slug, success)
        
        # 写入 SoulMem
        summary = f"[SOP 使用] {sop['name']} v{sop['version']}"
        detail = f"触发词: {', '.join(sop.get('triggers', []))}\n"
        detail += f"步骤数: {len(sop.get('steps', []))}\n"
        detail += f"结果: {'成功' if success else '失败'}\n"
        if notes:
            detail += f"备注: {notes}\n"
        
        tags = json.dumps(["sop", slug, "usage"], ensure_ascii=False)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("约定", summary, detail, tags, 6, datetime.now().strftime("%Y-%m-%d")))
        
        memory_id = cur.lastrowid
        self.conn.commit()
        
        return memory_id
    
    def on_sop_created(self, slug: str):
        """
        SOP 被创建时，自动写入 SoulMem
        """
        from sop_manager import SOPManager
        manager = SOPManager()
        sop = manager.get_sop(slug)
        
        if not sop:
            return None
        
        summary = f"[SOP 创建] {sop['name']}"
        detail = f"描述: {sop.get('description', '')}\n"
        detail += f"步骤: {len(sop.get('steps', []))} 步\n"
        detail += f"触发词: {', '.join(sop.get('triggers', []))}\n"
        
        if sop.get("gotchas"):
            detail += f"已知问题: {len(sop['gotchas'])} 个\n"
        
        tags = json.dumps(["sop", slug, "creation"], ensure_ascii=False)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("约定", summary, detail, tags, 7, datetime.now().strftime("%Y-%m-%d")))
        
        memory_id = cur.lastrowid
        self.conn.commit()
        
        return memory_id
    
    def on_sop_updated(self, slug: str, changes: str):
        """
        SOP 被更新时，自动写入 SoulMem
        """
        from sop_manager import SOPManager
        manager = SOPManager()
        sop = manager.get_sop(slug)
        
        if not sop:
            return None
        
        summary = f"[SOP 更新] {sop['name']} v{sop['version']}"
        detail = f"变更: {changes}\n"
        
        tags = json.dumps(["sop", slug, "update"], ensure_ascii=False)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("约定", summary, detail, tags, 5, datetime.now().strftime("%Y-%m-%d")))
        
        memory_id = cur.lastrowid
        self.conn.commit()
        
        return memory_id
    
    def on_gotcha_found(self, slug: str, problem: str, solution: str):
        """
        发现新的 gotcha 时，自动写入 SoulMem + triples
        """
        from sop_manager import SOPManager
        manager = SOPManager()
        sop = manager.get_sop(slug)
        
        if not sop:
            return None
        
        # 写入 episodic_memory
        summary = f"[SOP 问题] {sop['name']}: {problem[:50]}"
        detail = f"问题: {problem}\n"
        detail += f"方案: {solution}\n"
        detail += f"SOP: {sop['name']} v{sop['version']}\n"
        
        tags = json.dumps(["sop", slug, "gotcha"], ensure_ascii=False)
        
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("错误", summary, detail, tags, 6, datetime.now().strftime("%Y-%m-%d")))
        
        memory_id = cur.lastrowid
        
        # 写入 triples
        cur.execute("""
            INSERT INTO triples (symptom, cause, solution, tags, domain, confidence, source)
            VALUES (?, ?, ?, ?, ?, 0.7, 'sop')
        """, (
            problem[:100],
            f"SOP {sop['name']} 已知问题",
            solution[:200],
            json.dumps(["sop", slug], ensure_ascii=False),
            "sop",
        ))
        
        self.conn.commit()
        
        return memory_id


# ========================================
# CLI 接口
# ========================================

def main():
    import argparse
    
    p = argparse.ArgumentParser(description="SoulMem SOP Funnel")
    sub = p.add_subparsers(dest="command")
    
    # used
    used_p = sub.add_parser("used", help="记录 SOP 使用")
    used_p.add_argument("slug", help="SOP slug")
    used_p.add_argument("--success", action="store_true", default=True)
    used_p.add_argument("--notes", default="")
    
    # created
    created_p = sub.add_parser("created", help="记录 SOP 创建")
    created_p.add_argument("slug", help="SOP slug")
    
    # updated
    updated_p = sub.add_parser("updated", help="记录 SOP 更新")
    updated_p.add_argument("slug", help="SOP slug")
    updated_p.add_argument("--changes", required=True)
    
    # gotcha
    gotcha_p = sub.add_parser("gotcha", help="记录新问题")
    gotcha_p.add_argument("slug", help="SOP slug")
    gotcha_p.add_argument("--problem", required=True)
    gotcha_p.add_argument("--solution", required=True)
    
    args = p.parse_args()
    
    if not args.command:
        p.print_help()
        return
    
    funnel = SOPFunnel()
    
    if args.command == "used":
        memory_id = funnel.on_sop_used(args.slug, args.success, args.notes)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")
    
    elif args.command == "created":
        memory_id = funnel.on_sop_created(args.slug)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")
    
    elif args.command == "updated":
        memory_id = funnel.on_sop_updated(args.slug, args.changes)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")
    
    elif args.command == "gotcha":
        memory_id = funnel.on_gotcha_found(args.slug, args.problem, args.solution)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")


if __name__ == "__main__":
    main()
