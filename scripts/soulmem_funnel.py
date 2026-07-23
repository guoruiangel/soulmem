#!/usr/bin/env python3
# ============================================================================
# SoulMem Funnel — 统一录入漏斗
# 入口: soulmem ingest [manual|pending|auto|review]
#
# 核心理念: 用户写一段话 → 漏斗自动拆解 → 自动写入
# ============================================================================

import os
import sys
import json
import sqlite3
import re
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, SCRIPTS_DIR)


# ============================================================
# 信号定义
# ============================================================

# 技术类信号模式
TECH_SYMPTOM_PATTERNS = [
    r'(报错|错误|失败|error|ERROR|fail|FAIL|crash|exception)',
    r'(超时|timeout|TIMEOUT)',
    r'(不能|无法|没法|不行|不起作用|不工作)',
    r'(崩溃|crash|奔溃|挂掉|死掉)',
    r'(慢|卡顿|卡死|无响应|hang)',
    r'(连接不上|连不上|无法连接|connection refused)',
    r'(找不到|不存在|404|not found|No such file)',
    r'(权限|禁止|403|forbidden|permission)',
    r'(数据丢失|数据损坏|损坏|corrupt)',
    r'(配置错误|配置不对|配置缺失|misconfiguration)',
    r'(报500|500错误|500)',
    r'(问题|故障|bug|Bug|BUG)',
]

TECH_CAUSE_PATTERNS = [
    (r'(缺少|缺失|丢失|not found|No module)', '模块/文件缺失'),
    (r'(版本不兼容|版本冲突|version mismatch)', '版本问题'),
    (r'(配置错误|配置参数|config|setting)', '配置错误'),
    (r'(数据库|SQLite|MySQL|postgres|db|database)', '数据库问题'),
    (r'(API|接口|endpoint|route|URL)', 'API问题'),
    (r'(服务|进程|process|service|daemon)', '服务未运行'),
    (r'(网络|network|connection|socket|TCP|HTTP)', '网络问题'),
    (r'(权限|permission|access|auth|token)', '权限/认证问题'),
    (r'(内存|memory|OOM|out of memory)', '内存问题'),
    (r'(并发|线程|thread|race condition|deadlock)', '并发问题'),
    (r'(import|导入)(.{0,15})(失败|错误|断|丢失|问题)', '导入链断裂'),
    (r'(链|链路|依赖)(.{0,15})(断裂|断开|断|丢失|问题)', '依赖链断裂'),
    (r'(模块|文件|包)(.{0,10})(找不到|不存在|缺失|丢失)', '模块缺失'),
]

TECH_SOLUTION_PATTERNS = [
    (r'(重启|restart|reboot)', '重启服务'),
    (r'(修复|fix|patch|modify|update|upgrade)', '修复代码'),
    (r'(配置|config|set|parameter|ENV|environment)', '修改配置'),
    (r'(安装|install|pip|npm|brew)', '安装依赖'),
    (r'(清理|clear|clean|flush|purge)', '清理缓存/数据'),
    (r'(回滚|rollback|revert|downgrade)', '版本回滚'),
    (r'(重建|rebuild|recreate|init)', '重建资源'),
    (r'(建|创建|新建)(.{0,15})(stub|模块|文件|替代)', '创建替代模块'),
    (r'(替换|替代|换)(.{0,15})(模块|文件|方案)', '替换组件'),
    (r'(检查|检测|验证)(.{0,10})(import|导入|依赖)', '添加检查'),
]

EMOTION_KEYWORDS = {
    "开心": ["开心", "嘿嘿", "哈哈", "棒", "好耶"],
    "累": ["累", "疲惫", "疲", "困"],
    "烦": ["烦", "烦躁", "枯燥", "无聊"],
    "难过": ["难过", "伤心", "悲伤", "哭"],
    "生气": ["生气", "愤怒", "怒"],
    "失望": ["失望", "绝望"],
    "担心": ["担心", "焦虑", "不安"],
    "平静": ["平静", "安静", "淡定"],
    "期待": ["期待", "期望", "盼望"],
    "兴奋": ["兴奋", "激动", "澎湃"],
    "害羞": ["害羞", "羞怯", "腼腆"],
    "心疼": ["心疼", "怜惜", "同情"],
    "感动": ["感动", "触动"],
    "舒服": ["舒服", "舒适", "惬意"],
    "思念": ["想你", "思念", "想念"],
    "满足": ["满足", "满意", "知足"],
}

FEEDBACK_MAPPING = {
    "ok": {"effect": "success", "result": "完成", "keywords": ["ok", "可以", "对", "没错", "就是这样"]},
    "partial": {"effect": "partial", "result": "部分完成", "keywords": ["嗯", "还行", "凑合", "先这样"]},
    "fail": {"effect": "fail", "result": "需重做", "keywords": ["不行", "不对", "重来"]},
    "iterate": {"effect": "iterate", "result": "需改进", "keywords": ["再改改", "还差点"]},
    "abort": {"effect": "abort", "result": "终止", "keywords": ["算了", "不搞了", "不要"]},
}

DOMAIN_KEYWORDS = {
    "xiaoyu_scoring": ["小渔", "打分"],
    "linkclaw": ["LinkClaw", "linkclaw"],
    "wiki": ["wiki", "Wiki"],
    "pablo": ["Pablo", "pablo"],
    "iris": ["Iris", "iris"],
    "kk_homepage": ["5006", "主页", "积分"],
    "cron": ["cron", "Cron", "定时"],
    "gateway": ["gateway", "网关"],
}

TECH_TAGS = ['500', 'import', 'Flask', 'SQLite', 'LinkClaw', 'Ollama', 'Pablo', 'Iris',
             'wiki', 'memory', 'cron', 'gateway', 'deepseek', 'LongCat', 'API']


# ============================================================
# 漏斗引擎
# ============================================================

class FunnelEngine:
    """漏斗引擎：自动拆解用户输入，写入 SoulMem"""
    
    def __init__(self, role="kk"):
        self.role = role
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def ingest(self, text):
        """主拆解+写入流程"""
        if not text.strip():
            return {"ok": False, "error": "内容为空"}
        
        parsed = self.parse(text)
        validated = self.validate(parsed)
        self.display_draft(validated)
        return validated
    
    def parse(self, text):
        """自动拆解用户输入"""
        result = {
            "raw": text,
            "role": self.role,
            "parsed_at": datetime.now().isoformat(),
        }
        result.update(self._parse_text(text))
        return result
    
    def _parse_text(self, text):
        """统一的文本解析"""
        result = {}
        
        # 症状/问题
        for p in TECH_SYMPTOM_PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                result["symptom"] = "功能异常"
                break
        
        # 根因
        for pattern, label in TECH_CAUSE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                result["cause"] = label
                break
        
        # 方案
        for pattern, label in TECH_SOLUTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                result["solution"] = label
                break
        
        # 情绪
        emotions = []
        for emotion, keywords in EMOTION_KEYWORDS.items():
            if any(k in text for k in keywords):
                emotions.append(emotion)
        if emotions:
            result["emotions"] = emotions
        
        # 反馈
        for fb_type, fb_data in FEEDBACK_MAPPING.items():
            if any(k in text for k in fb_data["keywords"]):
                result["feedback"] = fb_data
                break
        
        # 偏好
        pref_patterns = [
            r'喜欢(.{1,15})', r'爱(.{1,15})', r'不喜欢(.{1,15})',
            r'讨厌(.{1,15})', r'想要(.{1,15})', r'希望(.{1,15})',
        ]
        for p in pref_patterns:
            m = re.search(p, text)
            if m:
                result["preference"] = m.group(1).strip()
                break
        
        # 域
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(k in text for k in keywords):
                result["domain"] = domain
                break
        
        # 标签
        tags = [t for t in TECH_TAGS if t.lower() in text.lower()]
        if tags:
            result["tags"] = tags
        
        # 摘要和详细
        lines = text.strip().split('\n')
        result["summary"] = lines[0][:100] if lines else text[:100]
        result["detail"] = text
        result["scene_type"] = "错误" if result.get("symptom") else "任务"
        result["importance"] = 5
        
        return result
    
    def validate(self, parsed):
        """校验+自动补全"""
        validated = dict(parsed)
        if not validated.get("summary"):
            validated["summary"] = validated.get("raw", "")[:100]
        if not validated.get("tags"):
            validated["tags"] = []
        return validated
    
    def display_draft(self, validated):
        """展示草稿"""
        print("\n" + "=" * 50)
        print("📋 解析结果:")
        print("=" * 50)
        print(f"  摘要: {validated.get('summary', '-')[:60]}")
        
        if validated.get("symptom"):
            print(f"  症状: {validated['symptom']}")
        if validated.get("cause"):
            print(f"  根因: {validated['cause']}")
        if validated.get("solution"):
            print(f"  方案: {validated['solution']}")
        if validated.get("emotions"):
            print(f"  情绪: {', '.join(validated['emotions'])}")
        if validated.get("feedback"):
            print(f"  反馈: {validated['feedback']['effect']} → {validated['feedback']['result']}")
        if validated.get("preference"):
            print(f"  偏好: {validated['preference']}")
        if validated.get("domain"):
            print(f"  域: {validated['domain']}")
        if validated.get("tags"):
            print(f"  标签: {', '.join(validated['tags'])}")
        
        print("=" * 50)
    
    def write(self, validated):
        """写入数据库"""
        written = []
        
        # 写入 episodic_memory
        tags = json.dumps(validated.get("tags", []), ensure_ascii=False)
        self.conn.execute("""
            INSERT INTO episodic_memory (scene_type, summary, detail, tags, importance, memory_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            validated.get("scene_type", "任务"),
            validated.get("summary", ""),
            validated.get("detail", ""),
            tags,
            validated.get("importance", 5),
            datetime.now().strftime("%Y-%m-%d"),
        ))
        written.append(f"episodic_memory #{self.conn.execute('SELECT last_insert_rowid()').fetchone()[0]}")
        
        # 写入三元组（如果有症状+根因）
        if validated.get("symptom") and validated.get("cause"):
            self.conn.execute("""
                INSERT INTO triples (symptom, cause, solution, tags, domain, confidence, source)
                VALUES (?, ?, ?, ?, ?, 0.6, 'funnel')
            """, (
                validated.get("summary", "")[:100],
                validated["cause"],
                validated.get("solution", "待补充"),
                json.dumps(validated.get("tags", []), ensure_ascii=False),
                validated.get("domain", "general"),
            ))
            written.append(f"triples #{self.conn.execute('SELECT last_insert_rowid()').fetchone()[0]}")
        
        self.conn.commit()
        return written


# ============================================================
# 子命令处理
# ============================================================

def cmd_ingest(args):
    """soulmem ingest 子命令"""
    import json
    from datetime import timedelta
    from funnel_generator import ReportGenerator
    from funnel_cron import run_period_check, get_current_period
    
    ingest_cmd = getattr(args, 'ingest_cmd', None)
    
    if ingest_cmd == 'manual':
        _cmd_ingest_manual(args)
    elif ingest_cmd == 'pending':
        _cmd_ingest_pending()
    elif ingest_cmd == 'auto':
        _cmd_ingest_auto()
    elif ingest_cmd == 'review':
        _cmd_ingest_review(args)
    else:
        print("Usage: soulmem ingest <command>")
        print("")
        print("Commands:")
        print("  manual [--role kk|iris]     手动录入")
        print("  pending                    查看待审核报告")
        print("  auto                       触发自动分析")
        print("  review <report_id>         审核报告")


def _cmd_ingest_manual(args):
    """手动录入模式"""
    role = getattr(args, 'role', 'kk')
    print(f"\n🔍 SoulMem Funnel — {role.upper()} 模式")
    print("=" * 50)
    print("📝 记录今天的事（写多少都行，写完按两次回车）:\n")
    
    lines = []
    while True:
        try:
            line = input()
            if line == '' and lines and lines[-1] == '':
                break
            lines.append(line)
        except EOFError:
            break
    
    text = '\n'.join(lines).strip()
    if not text:
        print("取消录入")
        return
    
    engine = FunnelEngine(role)
    result = engine.ingest(text)
    
    print(f"\n确认写入 SoulMem? [Y/n/e(编辑)]")
    choice = input("> ").strip().lower()
    
    if choice in ('y', ''):
        written = engine.write(result)
        print(f"\n✅ 已写入: {', '.join(written)}")
    elif choice == 'e':
        print("请输入补充内容:")
        extra = input("> ").strip()
        result["detail"] = result.get("detail", "") + "\n\n补充: " + extra
        written = engine.write(result)
        print(f"\n✅ 已写入: {', '.join(written)}")
    else:
        print("取消录入")


def _cmd_ingest_pending():
    """查看待审核报告"""
    generator = ReportGenerator()
    pending = generator.get_pending_reports()
    if not pending:
        print("📋 没有待审核的报告")
        return
    print(f"📋 {len(pending)} 个待审核报告:\n")
    for r in pending:
        data = json.loads(r["generated_content"])
        print(f"  #{r['id']} | {data.get('period', {}).get('start', '?')[:16]} | {data.get('summary', {}).get('total_conversations', 0)} 条")


def _cmd_ingest_auto():
    """触发自动分析"""
    period = get_current_period()
    if period:
        run_period_check(period)
    else:
        print("📋 当前不是检查时段，分析过去4小时...")
        generator = ReportGenerator()
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=4)
        report = generator.generate_period_report(start_time, end_time)
        if report:
            report_id = generator.save_pending_report(report)
            print(f"📋 发现 {report['summary']['total_conversations']} 条有价值内容")
            print(f"报告已保存 #{report_id}，请审核")
        else:
            print("📋 过去4小时无值得记录的内容")


def _cmd_ingest_review(args):
    """审核报告"""
    report_id = args.report_id
    generator = ReportGenerator()
    
    cursor = generator.conn.execute("SELECT * FROM pending_reports WHERE id = ?", (report_id,))
    report = cursor.fetchone()
    if not report:
        print(f"❌ 报告 #{report_id} 不存在")
        return
    
    data = json.loads(report["generated_content"])
    print(generator.format_report(data))
    
    print(f"\n操作: [a]通过 [e]编辑 [r]拒绝 [s]跳过")
    choice = input("> ").strip().lower()
    
    if choice == 'a':
        generator.approve_report(report_id)
        print(f"✅ 报告 #{report_id} 已通过")
        written = generator.write_to_soulmem(report_id)
        if written:
            print(f"✅ 已自动写入 SoulMem")
    elif choice == 'e':
        print("请输入编辑后的内容:")
        edited = input("> ").strip()
        generator.approve_report(report_id, edited)
        print(f"✅ 报告 #{report_id} 已编辑并通过")
    elif choice == 'r':
        generator.reject_report(report_id)
        print(f"✅ 报告 #{report_id} 已拒绝")
    else:
        print("跳过")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='SoulMem Funnel — 统一录入漏斗')
    p.add_argument('command', nargs='?', default='help', choices=['manual', 'pending', 'auto', 'review', 'help'])
    p.add_argument('--role', default='kk', choices=['kk', 'iris'])
    p.add_argument('report_id', nargs='?', type=int, default=None)
    args = p.parse_args()
    cmd_ingest(args)
