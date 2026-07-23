#!/usr/bin/env python3
# ============================================================================
# SoulMem Funnel — 三时段检查触发器
# 14:00 检查 9:30-14:00
# 19:00 检查 14:00-19:00
# 24:00 检查 19:00-24:00
# ============================================================================

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = os.environ.get("SOUL_MEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, SCRIPTS_DIR)

from funnel_generator import ReportGenerator


# 时段配置
PERIODS = [
    {
        "name": "早班",
        "check_time": "14:00",
        "start_hour": 9, "start_minute": 30,
        "end_hour": 14, "end_minute": 0,
    },
    {
        "name": "下午班",
        "check_time": "19:00",
        "start_hour": 14, "start_minute": 0,
        "end_hour": 19, "end_minute": 0,
    },
    {
        "name": "晚班",
        "check_time": "00:00",
        "start_hour": 19, "start_minute": 0,
        "end_hour": 23, "end_minute": 59,
    },
]


def get_current_period():
    """获取当前检查时段"""
    now = datetime.now()
    current_time = now.hour * 60 + now.minute  # 当前分钟数
    
    for period in PERIODS:
        check_parts = period["check_time"].split(":")
        check_minutes = int(check_parts[0]) * 60 + int(check_parts[1])
        
        # 允许 ±5 分钟的误差
        if abs(current_time - check_minutes) <= 5:
            return period
    
    return None


def run_period_check(period):
    """执行时段检查"""
    now = datetime.now()
    
    # 计算时段起止时间
    start_time = now.replace(
        hour=period["start_hour"],
        minute=period["start_minute"],
        second=0,
        microsecond=0
    )
    end_time = now.replace(
        hour=period["end_hour"],
        minute=period["end_minute"],
        second=0,
        microsecond=0
    )
    
    # 晚班的结束时间是 23:59
    if period["name"] == "晚班":
        end_time = now.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # 如果当前时间早于时段开始，说明是检查上一时段
    if now < start_time:
        start_time -= timedelta(days=1)
        end_time -= timedelta(days=1)
    
    # 生成报告
    generator = ReportGenerator()
    report = generator.generate_period_report(start_time, end_time)
    
    if report:
        # 保存到待审核表
        report_id = generator.save_pending_report(report)
        
        # 输出结果
        print(f"📋 {period['name']}检查完成 ({start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')})")
        print(f"发现 {report['summary']['total_conversations']} 条有价值内容")
        print(f"报告已保存 #{report_id}，请审核")
        
        return report_id
    else:
        print(f"📋 {period['name']}检查完成 ({start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')})")
        print("无值得记录的内容")
        
        return None


def run_all_periods():
    """运行所有时段检查（测试用）"""
    generator = ReportGenerator()
    
    for period in PERIODS:
        start_time = datetime.now().replace(
            hour=period["start_hour"],
            minute=period["start_minute"],
            second=0,
            microsecond=0
        )
        end_time = datetime.now().replace(
            hour=period["end_hour"],
            minute=period["end_minute"],
            second=0,
            microsecond=0
        )
        
        if period["name"] == "晚班":
            end_time = end_time.replace(hour=23, minute=59, second=59)
        
        # 检查过去24小时的数据（测试用）
        start_time -= timedelta(days=1)
        
        report = generator.generate_period_report(start_time, end_time)
        
        print(f"\n{'='*50}")
        print(f"时段: {period['name']} ({period['start_hour']}:{period['start_minute']:02d}-{period['end_hour']}:{period['end_minute']:02d})")
        
        if report:
            print(f"有价值内容: {report['summary']['total_conversations']} 条")
            print(f"总权重: {report['summary']['total_weight']}")
        else:
            print("无值得记录的内容")


if __name__ == "__main__":
    import argparse
    
    p = argparse.ArgumentParser(description='SoulMem Funnel — 三时段检查')
    p.add_argument("--test", action="store_true", help="测试所有时段")
    p.add_argument("--check", action="store_true", help="执行当前时段检查")
    
    args = p.parse_args()
    
    if args.test:
        run_all_periods()
    elif args.check:
        period = get_current_period()
        if period:
            run_period_check(period)
        else:
            print("当前不是检查时段 (14:00/19:00/00:00)")
    else:
        # 默认执行当前时段检查
        period = get_current_period()
        if period:
            run_period_check(period)
        else:
            print("当前不是检查时段 (14:00/19:00/00:00)")
