#!/usr/bin/env python3
# ============================================================================
# SoulMem — Auto Remediation Engine
# Takes a problem description, finds matching SOP, executes steps,
# records results, and solidifies the experience.
#
# Usage:
#   python3 scripts/auto_remediate.py "500 error on KK page"
#   python3 scripts/auto_remediate.py run <sop_id>
#   python3 scripts/auto_remediate.py interactive
# ============================================================================
import os, sys, json, sqlite3, subprocess, re
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, SCRIPTS_DIR)


class AutoRemediator:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
    
    def find_sop(self, problem_description, top=3):
        """Find matching SOPs for a problem."""
        from troubleshooter import Troubleshooter
        ts = Troubleshooter()
        return ts.search_sop(problem_description, top)
    
    def find_similar_triples(self, problem_description, top=3):
        """Find similar triples from past fixes."""
        from triples_v2 import TripleStoreV2
        tsv2 = TripleStoreV2()
        return tsv2.search(problem_description, top)
    
    def execute_sop(self, sop_id, dry_run=False):
        """Execute a SOP step by step."""
        self.cur.execute("SELECT * FROM troubleshooting_sops WHERE id = ?", (sop_id,))
        sop = self.cur.fetchone()
        if not sop:
            print(f"❌ SOP #{sop_id} 不存在")
            return None
        
        steps = json.loads(sop['steps'])
        outcomes = json.loads(sop['expected_outcomes'])
        
        print(f"🔧 执行 SOP #{sop_id}: {sop['symptom']}")
        print(f"   类别: {sop['category']}")
        print(f"   步骤数: {len(steps)}")
        print(f"   预期结果: {', '.join(outcomes) if outcomes else '无'}")
        print("=" * 50)
        
        results = []
        for i, step in enumerate(steps, 1):
            print(f"\n  步骤 {i}/{len(steps)}: {step}")
            
            if dry_run:
                print(f"  [dry-run] 跳过执行")
                results.append({'step': step, 'status': 'skipped', 'output': ''})
                continue
            
            # Ask user what to do
            print(f"  选项: [e]执行命令 [s]跳过 [f]完成并标记成功 [q]退出")
            choice = input("  > ").strip().lower()
            
            if choice == 'e':
                cmd = input("  输入命令: ").strip()
                if cmd:
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                        output = result.stdout.strip() or result.stderr.strip()
                        print(f"  输出: {output[:200]}")
                        results.append({'step': step, 'status': 'executed', 'output': output, 'command': cmd})
                    except Exception as e:
                        print(f"  错误: {e}")
                        results.append({'step': step, 'status': 'error', 'output': str(e)})
                else:
                    results.append({'step': step, 'status': 'skipped', 'output': ''})
            elif choice == 's':
                results.append({'step': step, 'status': 'skipped', 'output': ''})
            elif choice == 'f':
                results.append({'step': step, 'status': 'completed', 'output': ''})
                break
            elif choice == 'q':
                return None
        
        return {
            'sop_id': sop_id,
            'symptom': sop['symptom'],
            'steps_results': results,
            'executed_at': datetime.now().isoformat()
        }
    
    def solidify_execution(self, execution_result, success=True):
        """Convert execution result into a triple."""
        if not execution_result:
            return None
        
        symptom = execution_result['symptom']
        steps_taken = [r['step'] for r in execution_result['steps_results'] if r['status'] != 'skipped']
        commands_run = [r.get('command', '') for r in execution_result['steps_results'] if r.get('command')]
        
        cause = f"执行了 {len(steps_taken)} 个步骤"
        solution = " → ".join(steps_taken[:5])
        if commands_run:
            solution += f"\n命令: {'; '.join(commands_run[:3])}"
        
        tags = ['auto-remediated', 'sop-execution']
        if success:
            tags.append('success')
        else:
            tags.append('failed')
        
        from triples_v2 import TripleStoreV2
        tsv2 = TripleStoreV2()
        tid = tsv2.add(
            symptom=f"[自动修复] {symptom}",
            cause=cause,
            solution=solution,
            tags=tags,
            domain='auto-remediation',
            confidence=0.7 if success else 0.4,
            source='auto-remediator'
        )
        
        return tid
    
    def auto_diagnose(self, problem_description):
        """Full pipeline: search SOP → search triples → suggest action."""
        print(f"🔍 诊断: {problem_description}\n")
        
        # 1. Find matching SOPs
        sops = self.find_sop(problem_description)
        triples = self.find_similar_triples(problem_description)
        
        suggestions = []
        
        if sops:
            print(f"📋 找到 {len(sops)} 个排查SOP:")
            for sop in sops:
                print(f"  #{sop['id']} {sop['symptom']} (成功{sop['success_count']}次)")
                suggestions.append(('sop', sop))
        
        if triples:
            print(f"\n📚 找到 {len(triples)} 条相关经验:")
            for t in triples:
                print(f"  #{t['id']} {t['symptom'][:60]} (置信{t['confidence']})")
                suggestions.append(('triple', t))
        
        if not suggestions:
            print("❌ 没有找到匹配的SOP或经验")
            return None
        
        return suggestions


def cmd_run(args):
    """Run a SOP by ID."""
    ar = AutoRemediator()
    dry_run = args.dry_run if hasattr(args, 'dry_run') else False
    result = ar.execute_sop(args.sop_id, dry_run)
    
    if result and not dry_run:
        success = input("\n✅ 问题是否解决? (y/N): ").strip().lower() == 'y'
        tid = ar.solidify_execution(result, success)
        if tid:
            print(f"✅ 经验已沉淀为三元组 #{tid}")
        
        # Record SOP result
        from troubleshooter import Troubleshooter
        ts = Troubleshooter()
        ts.record_result(args.sop_id, success)
        print(f"✅ SOP #{args.sop_id} 结果已记录")


def cmd_diagnose(args):
    """Auto-diagnose a problem."""
    ar = AutoRemediator()
    suggestions = ar.auto_diagnose(args.problem)
    
    if suggestions:
        print(f"\n💡 建议:")
        for type_, item in suggestions[:3]:
            if type_ == 'sop':
                print(f"  运行 SOP #{item['id']}: python3 scripts/auto_remediate.py run {item['id']}")
            else:
                print(f"  参考经验 #{item['id']}: {item['symptom'][:50]}")


def cmd_interactive(args):
    """Interactive troubleshooting session."""
    print("🔧 SoulMem 交互式排查")
    print("=" * 50)
    
    problem = input("\n📝 描述你遇到的问题: ").strip()
    if not problem:
        return
    
    ar = AutoRemediator()
    suggestions = ar.auto_diagnose(problem)
    
    if not suggestions:
        print("❌ 没有匹配的SOP，尝试用 triples 搜索")
        from triples_v2 import TripleStoreV2
        tsv2 = TripleStoreV2()
        triples = tsv2.search(problem, top=5)
        if triples:
            print(f"\n📚 相关经验:")
            for t in triples:
                print(f"  #{t['id']} | 症状: {t['symptom'][:60]}")
                print(f"       根因: {t['cause'][:60]}")
                print(f"       方案: {t['solution'][:60]}")
        return
    
    # Ask user to pick a SOP
    sops = [s for t, s in suggestions if t == 'sop']
    if sops:
        print(f"\n选择要执行的SOP (1-{len(sops)}):")
        for i, sop in enumerate(sops, 1):
            print(f"  {i}. #{sop['id']} {sop['symptom']}")
        
        choice = input("\n> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(sops):
            selected = sops[int(choice) - 1]
            result = ar.execute_sop(selected['id'])
            
            if result:
                success = input("\n✅ 问题是否解决? (y/N): ").strip().lower() == 'y'
                tid = ar.solidify_execution(result, success)
                if tid:
                    print(f"✅ 经验已沉淀为三元组 #{tid}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Auto Remediation Engine')
    sub = p.add_subparsers(dest='command')
    
    p_run = sub.add_parser('run', help='Run a SOP')
    p_run.add_argument('sop_id', type=int)
    p_run.add_argument('--dry-run', action='store_true')
    
    p_diag = sub.add_parser('diagnose', help='Diagnose a problem')
    p_diag.add_argument('problem', help='Problem description')
    
    sub.add_parser('interactive', help='Interactive session')
    
    args = p.parse_args()
    cmds = {'run': cmd_run, 'diagnose': cmd_diagnose, 'interactive': cmd_interactive}
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
