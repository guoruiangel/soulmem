#!/usr/bin/env python3
# ============================================================================
# SoulMem — SOP Triggers
# 三种触发模式: 人工发起 / OpenClaw发起 / 自动识别
# ============================================================================

import os
import sys
import json
import sqlite3
import re
from datetime import datetime
from typing import Optional, Dict, List

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

# 触发模式
TRIGGER_MODES = {
    "manual": "人工发起",      # 用户主动说"记住这个流程"
    "agent": "OpenClaw发起",  # OpenClaw 判断需要固化
    "auto": "自动识别",       # 同类操作做了 2+ 次
}


class SOPTriggerDetector:
    """SOP 触发检测器"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    # ========================================
    # 模式 1: 人工发起
    # ========================================
    
    def manual_trigger(self, text: str) -> Optional[str]:
        """
        检测用户是否主动要求固化
        
        Returns:
            sop_name or None
        """
        triggers = [
            "记住这个流程", "记下来", "固化", "SOP", "标准流程",
            "以后这么做", "整理一下", "写成 SOP",
        ]
        
        for t in triggers:
            if t in text:
                # 提取 SOP 名称（如果用户指定了）
                name = self._extract_sop_name(text)
                return name
        
        return None
    
    def _extract_sop_name(self, text: str) -> Optional[str]:
        """从文本中提取 SOP 名称"""
        patterns = [
            r'(?:关于|针对|给)(.+?)(?:的|做|整理)',
            r'(.+?)(?:的|标准)?(?:流程|SOP|步骤)',
            r'(.+?)(?:怎么|如何)(?:做|操作)',
        ]
        
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        
        return None
    
    # ========================================
    # 模式 2: OpenClaw 判断发起
    # ========================================
    
    def agent_trigger(self, session_history: List[Dict]) -> Optional[Dict]:
        """
        OpenClaw 根据会话内容判断是否需要固化
        
        Returns:
            suggestion or None
        """
        if not session_history:
            return None
        
        full_text = " ".join([m.get("text", "") for m in session_history])
        
        # 信号: 操作中遇到多个问题
        problem_signals = [
            "又出问题了", "上次也是", "这个 bug", "又错了",
            "搞错了", "不对", "重来", "失败了",
        ]
        
        problem_count = sum(1 for s in problem_signals if s in full_text)
        
        if problem_count >= 2:
            return {
                "mode": "agent",
                "reason": f"检测到 {problem_count} 个问题信号",
                "suggestion": "建议创建 SOP，避免重复踩坑",
            }
        
        # 信号: 复杂的操作序列
        if len(session_history) > 10:
            # 检查是否有重复操作
            actions = [m.get("text", "") for m in session_history if m.get("role") == "assistant"]
            if len(actions) > 5:
                return {
                    "mode": "agent",
                    "reason": f"复杂操作序列 ({len(actions)} 个动作)",
                    "suggestion": "建议创建 SOP，固化操作流程",
                }
        
        return None
    
    # ========================================
    # 模式 3: 自动识别
    # ========================================
    
    def auto_trigger(self) -> List[Dict]:
        """
        检测重复操作模式，自动建议创建 SOP
        
        Returns:
            list of suggestions
        """
        cur = self.conn.cursor()
        
        # 查找高频标签
        cur.execute("""
            SELECT tag, COUNT(*) as cnt
            FROM memory_tags_index
            GROUP BY tag
            HAVING cnt >= 2
            ORDER BY cnt DESC
        """)
        
        repeated_tags = [{"tag": r["tag"], "count": r["cnt"]} for r in cur.fetchall()]
        
        # 过滤掉已有 SOP 的标签
        existing_triggers = self._get_existing_triggers()
        
        suggestions = []
        for rt in repeated_tags:
            if rt["tag"].lower() not in existing_triggers:
                suggestions.append({
                    "mode": "auto",
                    "tag": rt["tag"],
                    "count": rt["count"],
                    "suggestion": f"标签「{rt['tag']}」出现 {rt['count']} 次，建议创建 SOP",
                })
        
        return suggestions
    
    def _get_existing_triggers(self) -> set:
        """获取已有 SOP 的触发词"""
        from sop_manager import SOPManager
        manager = SOPManager()
        
        triggers = set()
        for sop in manager.list_sops("all"):
            for t in sop.get("triggers", []):
                triggers.add(t.lower())
        
        return triggers
    
    # ========================================
    # 综合检测
    # ========================================
    
    def detect(self, text: str = None, session_history: List[Dict] = None) -> Dict:
        """
        综合检测，返回最优先的建议
        
        Returns:
            detection result
        """
        result = {
            "triggered": False,
            "mode": None,
            "suggestion": None,
        }
        
        # 优先级 1: 人工发起
        if text:
            manual = self.manual_trigger(text)
            if manual:
                result["triggered"] = True
                result["mode"] = "manual"
                result["sop_name"] = manual
                result["suggestion"] = f"人工发起: 创建 SOP「{manual}」"
                return result
        
        # 优先级 2: OpenClaw 判断
        if session_history:
            agent = self.agent_trigger(session_history)
            if agent:
                result["triggered"] = True
                result["mode"] = "agent"
                result["suggestion"] = f"OpenClaw 建议: {agent['suggestion']}"
                return result
        
        # 优先级 3: 自动识别
        auto = self.auto_trigger()
        if auto:
            result["triggered"] = True
            result["mode"] = "auto"
            result["suggestion"] = f"自动识别: {auto[0]['suggestion']}"
            result["auto_suggestions"] = auto
            return result
        
        return result


# ========================================
# CLI 接口
# ========================================

def main():
    import argparse
    
    p = argparse.ArgumentParser(description="SoulMem SOP Triggers")
    sub = p.add_subparsers(dest="command")
    
    # detect
    detect_p = sub.add_parser("detect", help="检测是否需要创建 SOP")
    detect_p.add_argument("--text", default=None, help="检测文本")
    
    # auto
    sub.add_parser("auto", help="自动识别重复操作")
    
    # test-manual
    test_p = sub.add_parser("test-manual", help="测试人工触发")
    test_p.add_argument("text", help="测试文本")
    
    args = p.parse_args()
    
    if not args.command:
        p.print_help()
        return
    
    detector = SOPTriggerDetector()
    
    if args.command == "detect":
        result = detector.detect(text=args.text)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "auto":
        suggestions = detector.auto_trigger()
        if not suggestions:
            print("暂无重复操作需要固化")
            return
        print(f"发现 {len(suggestions)} 个建议:")
        for s in suggestions:
            print(f"  - {s['suggestion']}")
    
    elif args.command == "test-manual":
        result = detector.manual_trigger(args.text)
        if result:
            print(f"✅ 人工触发: {result}")
        else:
            print("❌ 未触发")


if __name__ == "__main__":
    main()
