#!/usr/bin/env python3
# ============================================================================
# SoulMem Funnel — 报告生成器
# 自动分析对话历史，生成待审核报告
# ============================================================================

import os
import sys
import json
import sqlite3
import re
from datetime import datetime, timedelta
from collections import Counter

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, SCRIPTS_DIR)

from funnel_signals import has_value, extract_value_dimensions


class ReportGenerator:
    """自动分析对话历史，生成报告"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def generate_period_report(self, start_time, end_time):
        """
        生成指定时段的报告
        
        Args:
            start_time: 时段开始时间
            end_time: 时段结束时间
            
        Returns:
            dict: 报告数据
        """
        # 1. 拉取时段内的所有会话记录
        conversations = self._fetch_conversations(start_time, end_time)
        
        if not conversations:
            return None
        
        # 2. 筛选有价值的对话
        valuable_convos = []
        for conv in conversations:
            is_valuable, signals, weight = has_value(conv.get("detail", conv.get("summary", "")))
            if is_valuable:
                valuable_convos.append({
                    "conversation": conv,
                    "signals": signals,
                    "weight": weight,
                })
        
        if not valuable_convos:
            return None
        
        # 3. 生成报告
        report = self._build_report(valuable_convos, start_time, end_time)
        
        return report
    
    def _fetch_conversations(self, start_time, end_time):
        """
        获取指定时段内的对话记录
        
        数据来源:
        1. episodic_memory 表（已有记录）
        2. 会话历史（需要 sessions_history API）
        
        这里先从 episodic_memory 表中获取已标记的记录
        """
        # 从 episodic_memory 表中获取
        cursor = self.conn.execute("""
            SELECT id, scene_type, summary, detail, tags, importance, memory_date, created_at
            FROM episodic_memory
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY importance DESC, created_at DESC
        """, (start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S")))
        
        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "id": row["id"],
                "scene_type": row["scene_type"],
                "summary": row["summary"],
                "detail": row["detail"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "importance": row["importance"],
                "memory_date": row["memory_date"],
                "created_at": row["created_at"],
            })
        
        return conversations
    
    def _build_report(self, valuable_convos, start_time, end_time):
        """构建报告"""
        # 统计
        total_conversations = len(valuable_convos)
        total_weight = sum(c["weight"] for c in valuable_convos)
        signal_counter = Counter()
        for conv in valuable_convos:
            signal_counter.update(conv["signals"])
        
        # 提取维度
        dimensions = extract_value_dimensions(
            " ".join([c["conversation"].get("detail", c["conversation"].get("summary", "")) for c in valuable_convos])
        )
        
        # 分类
        categories = self._categorize(valuable_convos)
        
        report = {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "summary": {
                "total_conversations": total_conversations,
                "total_weight": total_weight,
                "top_signals": signal_counter.most_common(5),
                "dimensions": dimensions,
            },
            "categories": categories,
            "conversations": [
                {
                    "id": c["conversation"]["id"],
                    "summary": c["conversation"]["summary"],
                    "signals": c["signals"],
                    "weight": c["weight"],
                }
                for c in valuable_convos[:10]  # 最多10条
            ],
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        
        return report
    
    def _categorize(self, valuable_convos):
        """分类统计"""
        categories = {
            "技术问题": 0,
            "决策记录": 0,
            "偏好发现": 0,
            "情绪变化": 0,
            "约定承诺": 0,
            "其他": 0,
        }
        
        for conv in valuable_convos:
            signals = conv["signals"]
            if "problem" in signals or "fix" in signals:
                categories["技术问题"] += 1
            elif "decision" in signals or "advice" in signals:
                categories["决策记录"] += 1
            elif "preference" in signals:
                categories["偏好发现"] += 1
            elif "emotion" in signals:
                categories["情绪变化"] += 1
            elif "promise" in signals:
                categories["约定承诺"] += 1
            else:
                categories["其他"] += 1
        
        return categories
    
    def format_report(self, report):
        """格式化为可读文本"""
        if not report:
            return "📋 本时段无值得记录的内容"
        
        lines = []
        lines.append("📋 时段检查报告")
        lines.append("=" * 50)
        lines.append(f"📅 时段: {report['period']['start'][:16]} - {report['period']['end'][:16]}")
        lines.append(f"📊 统计: {report['summary']['total_conversations']} 条有价值内容 (总权重: {report['summary']['total_weight']})")
        lines.append("")
        
        # 信号统计
        lines.append("🔍 主要信号:")
        for signal, count in report["summary"]["top_signals"][:5]:
            lines.append(f"  - {signal}: {count} 次")
        lines.append("")
        
        # 分类统计
        lines.append("📁 分类:")
        for cat, count in report["summary"]["categories"].items():
            if count > 0:
                lines.append(f"  - {cat}: {count} 条")
        lines.append("")
        
        # 详细内容
        lines.append("📝 详细内容:")
        for i, conv in enumerate(report["conversations"][:5], 1):
            lines.append(f"  [{i}] {conv['summary'][:60]}")
            lines.append(f"      信号: {', '.join(conv['convices'])}")
            lines.append("")
        
        lines.append("=" * 50)
        lines.append("是否写入 SoulMem? [Y/n/e(编辑)/s(跳过)]")
        
        return "\n".join(lines)
    
    def save_pending_report(self, report):
        """保存到待审核表"""
        # 确保 pending_reports 表存在
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL,
                generated_content TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                edited_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                written INTEGER DEFAULT 0
            )
        """)
        
        self.conn.execute("""
            INSERT INTO pending_reports (session_key, generated_content, status)
            VALUES (?, ?, 'pending')
        """, (
            "auto-generated",
            json.dumps(report, ensure_ascii=False),
        ))
        
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    def get_pending_reports(self):
        """获取所有待审核报告"""
        cursor = self.conn.execute("""
            SELECT * FROM pending_reports
            WHERE status = 'pending'
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]
    
    def approve_report(self, report_id, edited_content=None):
        """审核通过报告"""
        if edited_content:
            self.conn.execute("""
                UPDATE pending_reports
                SET status = 'edited', edited_content = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (edited_content, report_id))
        else:
            self.conn.execute("""
                UPDATE pending_reports
                SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (report_id,))
        
        self.conn.commit()
    
    def reject_report(self, report_id):
        """拒绝报告"""
        self.conn.execute("""
            UPDATE pending_reports
            SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (report_id,))
        
        self.conn.commit()
    
    def write_to_soulmem(self, report_id):
        """将审核通过的内容写入 SoulMem"""
        cursor = self.conn.execute("""
            SELECT * FROM pending_reports WHERE id = ?
        """, (report_id,))
        report = cursor.fetchone()
        
        if not report:
            return False
        
        content = report["edited_content"] or report["generated_content"]
        data = json.loads(content)
        
        # 写入 episodic_memory
        for conv in data.get("conversations", []):
            tags = json.dumps(conv.get("signals", []), ensure_ascii=False)
            self.conn.execute("""
                INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "场景",
                conv.get("summary", ""),
                conv.get("summary", ""),
                tags,
                conv.get("weight", 5),
                datetime.now().strftime("%Y-%m-%d"),
            ))
        
        # 标记为已写入
        self.conn.execute("""
            UPDATE pending_reports SET written = 1 WHERE id = ?
        """, (report_id,))
        
        self.conn.commit()
        return True


if __name__ == "__main__":
    # 测试：生成过去4小时的报告
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=4)
    
    generator = ReportGenerator()
    report = generator.generate_period_report(start_time, end_time)
    
    if report:
        print(generator.format_report(report))
    else:
        print("📋 本时段无值得记录的内容")
