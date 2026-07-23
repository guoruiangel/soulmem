#!/usr/bin/env python3
# ============================================================================
# SoulMem Funnel — 价值信号识别
# 判断一段对话是否包含值得录入 SoulMem 的内容
# 不问"这是技术还是生活"，只问"有没有留下值得记的东西"
# ============================================================================

import re

# 值得录入的信号模式
VALUE_SIGNALS = {
    # 决策信号
    "decision": {
        "patterns": [
            r'(决定|选择|定了|就用|选.{0,3}方案|还是.{0,3}吧|改成|改为)',
            r'(OK|ok|好的|可以|行|中|就这么办|搞定|定了)',
        ],
        "weight": 3,
    },
    
    # 建议信号
    "advice": {
        "patterns": [
            r'(建议|觉得.{0,5}可以|应该|需要|最好|不妨|试试)',
            r'(我.{0,3}想|我.{0,3}认为|其实|不如|要不)',
        ],
        "weight": 3,
    },
    
    # 偏好信号
    "preference": {
        "patterns": [
            r'(喜欢|爱|不喜欢|讨厌|想要|希望|偏好|习惯)',
            r'(觉得.{0,3}好看|觉得.{0,3}舒服|适合|不合适)',
        ],
        "weight": 3,
    },
    
    # 问题信号
    "problem": {
        "patterns": [
            r'(报500|500错误|500|报错|错误|失败|error|ERROR|fail|FAIL|crash|exception)',
            r'(超时|timeout|TIMEOUT)',
            r'(不能|无法|没法|不行|不起作用|不工作|崩溃|奔溃)',
            r'(慢|卡顿|无响应|连接不上|找不到|不存在|权限|数据丢失)',
            r'(出.{0,3}问题|故障|bug|Bug|BUG|挂了|挂了|死掉)',
        ],
        "weight": 4,
    },
    
    # 修复信号
    "fix": {
        "patterns": [
            r'(修复|fix|解决|处理|排查|定位|找到.{0,5}原因)',
            r'(重启|restart|重装|重新|替换|更新|升级|回滚)',
            r'(安装|配置|修改|删除|清理|添加|补充|替换)',
            r'(部署|上线|测试|验证|确认|检查)',
        ],
        "weight": 3,
    },
    
    # 情绪信号
    "emotion": {
        "patterns": [
            r'(开心|高兴|快乐|兴奋|激动|满足|满意|幸福)',
            r'(累|疲惫|疲|困|倦|烦|烦躁|枯燥|无聊)',
            r'(难过|伤心|悲伤|哭|失望|绝望|生气|愤怒)',
            r'(担心|焦虑|不安|害怕|恐惧|紧张|害羞|羞怯)',
            r'(心疼|怜惜|感动|触动|舒服|舒适|惬意|平静)',
            r'(期待|期望|盼望|思念|想念|思考|反思)',
        ],
        "weight": 2,
    },
    
    # 约定信号
    "promise": {
        "patterns": [
            r'(记住|记下来|写下来|别忘了|下次|以后|记得)',
            r'(约定|承诺|保证|一定|必须|千万|小心|注意)',
        ],
        "weight": 4,
    },
    
    # 反馈信号
    "feedback": {
        "patterns": [
            r'(OK|ok|好的|可以|行|没错|对|就是这样|嗯|还行)',
            r'(不行|不对|重来|再改改|还差点|算了|凑合|先这样)',
            r'(做得好|很棒|厉害|真棒|太棒了|完美|不错)',
        ],
        "weight": 2,
    },
    
    # 价值观信号
    "values": {
        "patterns": [
            r'(不能.{0,5}动|不能.{0,5}改|底线|原则|绝对|一定不)',
            r'(必须|应该|需要|值得|意义|目标|追求)',
        ],
        "weight": 3,
    },
    
    # 场景记忆信号
    "scene": {
        "patterns": [
            r'(今天|昨天|刚才|上次|之前|后来|今天|那天)',
            r'(早上|中午|下午|晚上|夜里|凌晨)',
        ],
        "weight": 1,
    },
}


def has_value(text):
    """判断文本是否包含值得录入的内容"""
    if not text or len(text.strip()) < 3:
        return False, [], 0
    
    matched_signals = []
    total_weight = 0
    
    for signal_name, signal_config in VALUE_SIGNALS.items():
        for pattern in signal_config["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                matched_signals.append(signal_name)
                total_weight += signal_config["weight"]
                break  # 每个信号只计一次
    
    # 权重 >= 3 认为有价值
    is_valuable = total_weight >= 3
    
    return is_valuable, matched_signals, total_weight


def extract_value_dimensions(text):
    """从文本中提取有价值的维度"""
    dimensions = {}
    
    # 背景/上下文
    context_patterns = [
        r'今天(.{2,20})(?:突然|发现|遇到|出了)',
        r'(?:早上|中午|下午|晚上)(.{2,20})',
        r'(?:刚才|之前|上次)(.{2,20})',
    ]
    for p in context_patterns:
        m = re.search(p, text)
        if m:
            dimensions["context"] = m.group(0)
            break
    
    # 问题
    problem_patterns = [
        r'(问题|故障|bug|报错|错误|失败)(.{2,30})',
        r'(不能|无法|不行)(.{2,20})',
    ]
    for p in problem_patterns:
        m = re.search(p, text)
        if m:
            dimensions["problem"] = m.group(0)
            break
    
    # 举措
    action_patterns = [
        r'(通过|经过|用了|做了)(.{2,30})(?:解决|修复|处理)',
        r'(修复|解决|处理|排查)(.{2,30})',
    ]
    for p in action_patterns:
        m = re.search(p, text)
        if m:
            dimensions["action"] = m.group(0)
            break
    
    # 效果
    effect_patterns = [
        r'(结果|效果|最终|后来)(.{2,30})(?:好|成功|OK|可以|解决)',
        r'(终于|最后)(.{2,30})(?:好|成功|OK|可以)',
    ]
    for p in effect_patterns:
        m = re.search(p, text)
        if m:
            dimensions["effect"] = m.group(0)
            break
    
    return dimensions


def is_valuable_conversation(messages):
    """判断一段对话是否值得录入"""
    if not messages:
        return False, [], 0
    
    # 合并所有消息文本
    full_text = " ".join([m.get("text", "") for m in messages])
    
    # 检查信号
    is_valuable, signals, weight = has_value(full_text)
    
    return is_valuable, signals, weight


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        "今天小渔打分系统又报500了。查了一下是 app.py 头部 import 链断了，建了个 stub 模块重启才好。",
        "嗯，好的。",
        "我觉得可以试试用更好的方式来解决这个问题，你觉得呢？",
        "郭锐说喜欢黑色衣服，觉得不需要太多装饰。",
        "不行，这个方案不行，重来。",
        "刚才加班到很晚，有点累，但项目终于上线了。",
        "建议在 CI 里加个 import 检查，防止以后再犯。",
    ]
    
    for text in test_cases:
        valuable, signals, weight = has_value(text)
        print(f"\n文本: {text[:50]}...")
        print(f"  有价值: {valuable} (权重: {weight})")
        print(f"  信号: {', '.join(signals)}")
