#!/usr/bin/env python3
# ============================================================================
# SoulMem — SOP Skills Manager
# SOP: Standard Operating Procedure — 操作能力的固化
#
# 三种触发模式:
#   1. 人工发起: 用户说"记住这个流程" → 立即创建 SOP
#   2. OpenClaw发起: OpenClaw 判断需要固化 → 推送建议
#   3. 自动识别: 同类操作做了 2+ 次 → 自动建议创建
#
# SOP 文件存储: ~/.openclaw/workspace/soulmem/sops/
# ============================================================================

import os
import sys
import json
import yaml
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SOPS_DIR = Path(WORKSPACE) / "soulmem" / "sops"
SOPS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")


class SOPManager:
    """SOP 管理器: 创建/更新/查询/废弃 SOP"""
    
    def __init__(self):
        self.sops_dir = SOPS_DIR
    
    # ========================================
    # CRUD
    # ========================================
    
    def create_sop(self, name: str, description: str, steps: List[Dict], 
                   triggers: List[str] = None, gotchas: List[Dict] = None) -> str:
        """
        创建新 SOP
        
        Args:
            name: SOP 名称
            description: 描述
            steps: 步骤列表 [{"check": "...", "action": "...", "on_fail": "..."}]
            triggers: 触发关键词
            gotchas: 常见问题 [{"problem": "...", "solution": "..."}]
        
        Returns:
            slug: SOP 标识符
        """
        slug = self._slugify(name)
        
        sop = {
            "name": name,
            "description": description,
            "version": 1,
            "created": datetime.now().isoformat(),
            "last_used": None,
            "success_count": 0,
            "fail_count": 0,
            "triggers": triggers or [],
            "steps": steps,
            "gotchas": gotchas or [],
            "memory_ids": [],
            "status": "active",  # active/deprecated/archived
        }
        
        self._save_sop(slug, sop)
        return slug
    
    def get_sop(self, slug: str) -> Optional[Dict]:
        """获取 SOP"""
        sop_file = self.sops_dir / f"{slug}.yaml"
        if not sop_file.exists():
            return None
        
        with open(sop_file) as f:
            return yaml.safe_load(f)
    
    def update_sop(self, slug: str, **kwargs) -> bool:
        """更新 SOP 字段"""
        sop = self.get_sop(slug)
        if not sop:
            return False
        
        for key, value in kwargs.items():
            if key in sop:
                sop[key] = value
        
        sop["version"] = sop.get("version", 1) + 1
        self._save_sop(slug, sop)
        return True
    
    def add_step(self, slug: str, step: Dict, position: int = -1) -> bool:
        """添加步骤"""
        sop = self.get_sop(slug)
        if not sop:
            return False
        
        if position == -1:
            sop["steps"].append(step)
        else:
            sop["steps"].insert(position, step)
        
        self._save_sop(slug, sop)
        return True
    
    def add_gotcha(self, slug: str, problem: str, solution: str) -> bool:
        """追加常见问题"""
        sop = self.get_sop(slug)
        if not sop:
            return False
        
        # 检查是否已存在
        for g in sop.get("gotchas", []):
            if g.get("problem") == problem:
                g["seen"] = g.get("seen", 1) + 1
                self._save_sop(slug, sop)
                return True
        
        sop.setdefault("gotchas", []).append({
            "problem": problem,
            "solution": solution,
            "seen": 1,
            "added": datetime.now().isoformat(),
        })
        
        self._save_sop(slug, sop)
        return True
    
    def record_usage(self, slug: str, success: bool = True):
        """记录使用结果"""
        sop = self.get_sop(slug)
        if not sop:
            return
        
        sop["last_used"] = datetime.now().isoformat()
        if success:
            sop["success_count"] = sop.get("success_count", 0) + 1
        else:
            sop["fail_count"] = sop.get("fail_count", 0) + 1
        
        self._save_sop(slug, sop)
    
    def deprecate_sop(self, slug: str, reason: str = ""):
        """废弃 SOP"""
        sop = self.get_sop(slug)
        if not sop:
            return
        
        sop["status"] = "deprecated"
        sop["deprecated_at"] = datetime.now().isoformat()
        sop["deprecated_reason"] = reason
        self._save_sop(slug, sop)
    
    # ========================================
    # 查询
    # ========================================
    
    def list_sops(self, status: str = "active") -> List[Dict]:
        """列出所有 SOP"""
        sops = []
        for f in sorted(self.sops_dir.glob("*.yaml")):
            with open(f) as f:
                sop = yaml.safe_load(f)
                if status == "all" or sop.get("status") == status:
                    sops.append(sop)
        return sops
    
    def search_sops(self, query: str) -> List[Dict]:
        """搜索 SOP"""
        results = []
        query_lower = query.lower()
        
        for f in self.sops_dir.glob("*.yaml"):
            with open(f) as f:
                sop = yaml.safe_load(f)
                # 匹配名称、描述、触发词
                if (query_lower in sop.get("name", "").lower() or
                    query_lower in sop.get("description", "").lower() or
                    any(query_lower in t.lower() for t in sop.get("triggers", []))):
                    results.append(sop)
        
        return results
    
    def find_by_trigger(self, text: str) -> Optional[Dict]:
        """根据触发词查找匹配的 SOP"""
        text_lower = text.lower()
        
        for f in self.sops_dir.glob("*.yaml"):
            with open(f) as f:
                sop = yaml.safe_load(f)
                if sop.get("status") != "active":
                    continue
                for trigger in sop.get("triggers", []):
                    if trigger.lower() in text_lower:
                        return sop
        
        return None
    
    # ========================================
    # 模式检测 (自动识别)
    # ========================================
    
    def detect_repeated_operations(self) -> List[Dict]:
        """
        检测重复操作模式
        
        从 episodic_memory 中提取标签，发现同类操作做了 2+ 次
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 获取所有标签
        cur.execute("SELECT tag, COUNT(*) as cnt FROM memory_tags_index GROUP BY tag HAVING cnt >= 2")
        repeated_tags = [{"tag": r["tag"], "count": r["cnt"]} for r in cur.fetchall()]
        
        conn.close()
        
        # 过滤掉已有 SOP 的标签
        existing_triggers = set()
        for sop in self.list_sops("all"):
            for t in sop.get("triggers", []):
                existing_triggers.add(t.lower())
        
        # 返回没有 SOP 的重复操作
        suggestions = []
        for rt in repeated_tags:
            if rt["tag"].lower() not in existing_triggers:
                suggestions.append(rt)
        
        return suggestions
    
    # ========================================
    # SOP → SoulMem
    # ========================================
    
    def sop_to_memory(self, slug: str) -> Optional[int]:
        """
        将 SOP 内容写入 SoulMem 记忆
        
        Returns:
            memory_id
        """
        sop = self.get_sop(slug)
        if not sop:
            return None
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # 构建记忆内容
        summary = f"[SOP] {sop['name']} v{sop['version']}"
        detail = f"{sop['description']}\n\n"
        detail += f"步骤: {len(sop.get('steps', []))} 步\n"
        detail += f"成功率: {sop.get('success_count', 0)}/{sop.get('success_count', 0) + sop.get('fail_count', 0)}\n"
        
        if sop.get("gotchas"):
            detail += f"\n常见问题:\n"
            for g in sop["gotchas"]:
                detail += f"  - {g['problem']}: {g['solution']}\n"
        
        tags = json.dumps(["sop", slug] + sop.get("triggers", []), ensure_ascii=False)
        
        cur.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("约定", summary, detail, tags, 7, datetime.now().strftime("%Y-%m-%d")))
        
        memory_id = cur.lastrowid
        
        # 更新 SOP 的 memory_ids
        sop.setdefault("memory_ids", []).append(memory_id)
        self._save_sop(slug, sop)
        
        conn.commit()
        conn.close()
        
        return memory_id
    
    # ========================================
    # 内部方法
    # ========================================
    
    def _save_sop(self, slug: str, sop: Dict):
        """保存 SOP 到文件"""
        sop_file = self.sops_dir / f"{slug}.yaml"
        with open(sop_file, 'w') as f:
            yaml.dump(sop, f, allow_unicode=True, sort_keys=False)
    
    def _slugify(self, text: str) -> str:
        """生成 slug"""
        text = text.lower().strip()
        text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-') or f"sop-{int(datetime.now().timestamp())}"


# ========================================
# CLI 接口
# ========================================

def main():
    import argparse
    
    p = argparse.ArgumentParser(description="SoulMem SOP Skills Manager")
    sub = p.add_subparsers(dest="command")
    
    # list
    list_p = sub.add_parser("list", help="列出所有 SOP")
    list_p.add_argument("--status", default="active", choices=["active", "all"])
    
    # get
    get_p = sub.add_parser("get", help="获取 SOP 详情")
    get_p.add_argument("slug", help="SOP slug")
    
    # search
    search_p = sub.add_parser("search", help="搜索 SOP")
    search_p.add_argument("query", help="搜索关键词")
    
    # create
    create_p = sub.add_parser("create", help="创建 SOP")
    create_p.add_argument("--name", required=True)
    create_p.add_argument("--desc", default="")
    create_p.add_argument("--triggers", nargs="*", default=[])
    
    # detect
    sub.add_parser("detect", help="检测重复操作，建议创建 SOP")
    
    # to-memory
    to_mem_p = sub.add_parser("to-memory", help="将 SOP 写入 SoulMem")
    to_mem_p.add_argument("slug", help="SOP slug")
    
    args = p.parse_args()
    
    if not args.command:
        p.print_help()
        return
    
    manager = SOPManager()
    
    if args.command == "list":
        sops = manager.list_sops(args.status)
        if not sops:
            print("暂无 SOP")
            return
        for sop in sops:
            print(f"  {sop.get('name'):30} v{sop.get('version', 1)} | {sop.get('status', 'active')} | 成功{sop.get('success_count', 0)}次")
    
    elif args.command == "get":
        sop = manager.get_sop(args.slug)
        if not sop:
            print(f"SOP '{args.slug}' 不存在")
            return
        print(json.dumps(sop, indent=2, ensure_ascii=False))
    
    elif args.command == "search":
        results = manager.search_sops(args.query)
        if not results:
            print("未找到匹配的 SOP")
            return
        for sop in results:
            print(f"  {sop.get('name'):30} | {sop.get('description', '')[:50]}")
    
    elif args.command == "create":
        slug = manager.create_sop(args.name, args.desc, [], args.triggers)
        print(f"✅ SOP 创建: {slug}")
    
    elif args.command == "detect":
        suggestions = manager.detect_repeated_operations()
        if not suggestions:
            print("暂无重复操作需要固化")
            return
        print(f"发现 {len(suggestions)} 个重复操作:")
        for s in suggestions:
            print(f"  - {s['tag']}: {s['count']} 次")
    
    elif args.command == "to-memory":
        memory_id = manager.sop_to_memory(args.slug)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")


if __name__ == "__main__":
    main()
