#!/usr/bin/env python3
# ============================================================================
# SoulMem Funnel — Iris 角色适配
# 适配 Iris 的生活/情感/关系记录场景
# ============================================================================

IRIS_FUNNEL_CONFIG = {
    "role": "iris",
    "domain": "life",
    
    # 录入提示
    "prompt": "📝 记录今天关于郭锐的事:",
    
    # 自动提取维度（Iris 专属）
    "extract_dimensions": [
        "emotion",        # 情绪状态
        "trigger",        # 触发事件
        "context",        # 场景背景
        "preference",     # 偏好发现
        "interaction",    # 互动细节
        "feedback",       # 郭锐的反馈
        "sensory",        # 感官细节
        "temperature",    # 情感温度
    ],
    
    # 写入目标优先级
    "write_targets": [
        "soul_temperature",   # 灵魂温度
        "emotion_events",     # 事件案例
        "growth_log",         # 成长日志
        "episodic_memory",    # 场景记忆
    ],
    
    # 情绪关键词映射
    "emotion_keywords": {
        "开心": "开心",
        "嘿嘿": "开心", 
        "棒": "满足",
        "厉害": "欣赏",
        "喜欢": "爱慕",
        "想你": "思念",
        "累": "疲惫",
        "难过": "难过",
        "不舒服": "不适",
        "生气": "愤怒",
        "失望": "失望",
        "害怕": "恐惧",
        "担心": "焦虑",
        "烦": "烦躁",
        "无聊": "空虚",
        "平静": "平静",
        "期待": "期待",
        "兴奋": "兴奋",
        "害羞": "羞怯",
        "心疼": "怜惜",
        "感动": "感动",
        "舒服": "舒适",
    },
    
    # 反馈语义映射
    "feedback_mapping": {
        # 正面反馈
        "ok": {"effect": "success", "result": "完成"},
        "可以": {"effect": "success", "result": "完成"},
        "对": {"effect": "success", "result": "完成"},
        "没错": {"effect": "success", "result": "完成"},
        "就是这样": {"effect": "success", "result": "完成"},
        "嗯": {"effect": "partial", "result": "待观察"},
        "还行": {"effect": "partial", "result": "部分完成"},
        "凑合": {"effect": "partial", "result": "待优化"},
        "先这样": {"effect": "partial", "result": "待优化"},
        # 负面反馈
        "不行": {"effect": "fail", "result": "需重做"},
        "不对": {"effect": "fail", "result": "需重做"},
        "重来": {"effect": "fail", "result": "需重做"},
        "再改改": {"effect": "iterate", "result": "需改进"},
        "还差点": {"effect": "iterate", "result": "需改进"},
        "算了": {"effect": "abort", "result": "终止"},
        "不搞了": {"effect": "abort", "result": "终止"},
        "不要": {"effect": "abort", "result": "终止"},
    },
    
    # 确认提示
    "confirm_prompt": "确认写入 SoulMem?",
    "privacy_hint": "💡 温馨提示: 郭锐的生活记忆是隐私，请妥善保护",
    
    # 自动建议规则
    "auto_suggest": {
        "preference": "检测到偏好，是否写入郭锐画像?",
        "emotion": "检测到情绪变化，是否记录?",
        "important_date": "检测到重要日期，是否提醒郭锐?",
        "health": "检测到作息异常，是否关心一下?",
        "relationship": "检测到人际互动，是否记录?",
    },
}

# ============================================================================
# Iris 专属维度提取
# ============================================================================

class IrisDimensionExtractor:
    """从对话历史中提取 Iris 关注的维度"""
    
    @staticmethod
    def extract_emotion(text):
        """提取情绪关键词"""
        emotions = []
        for keyword, emotion in IRIS_FUNNEL_CONFIG["emotion_keywords"].items():
            if keyword in text:
                emotions.append(emotion)
        return list(set(emotions)) if emotions else None
    
    @staticmethod
    def extract_feedback(text):
        """提取反馈语义"""
        for keyword, mapping in IRIS_FUNNEL_CONFIG["feedback_mapping"].items():
            if keyword in text:
                return mapping
        return None
    
    @staticmethod
    def extract_preference(text):
        """提取偏好信息"""
        patterns = [
            r'喜欢(.{1,10})',
            r'爱(.{1,10})',
            r'不喜欢(.{1,10})',
            r'讨厌(.{1,10})',
            r'想要(.{1,10})',
            r'希望(.{1,10})',
        ]
        import re
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return None
    
    @staticmethod
    def extract_sensory(text):
        """提取感官细节"""
        keywords = {
            "颜色": ["黑", "白", "红", "蓝", "绿", "紫", "金", "银", "透明"],
            "温度": ["热", "冷", "暖", "凉", "烫", "冰"],
            "触感": ["软", "硬", "滑", "粗", "紧", "松", "湿", "干"],
            "声音": ["轻", "重", "快", "慢", "柔", "脆", "沙", "哑"],
            "气味": ["香", "臭", "腥", "甜", "酸", "淡", "浓"],
        }
        found = {}
        for dimension, words in keywords.items():
            matches = [w for w in words if w in text]
            if matches:
                found[dimension] = matches
        return found if found else None


# ============================================================================
# Iris 报告生成器
# ============================================================================

class IrisReportGenerator:
    """生成 Iris 风格的会话分析报告"""
    
    def __init__(self):
        self.extractor = IrisDimensionExtractor()
    
    def generate(self, conversation_history):
        """
        分析对话历史，生成 Iris 风格的报告
        
        报告结构:
        1. 场景背景 (时间/地点/状态)
        2. 郭锐的情绪变化
        3. 互动细节 (感官/温度/节奏)
        4. 郭锐的反馈
        5. 效果判定
        6. 待改进
        """
        # 分离郭锐说的话和Iris说的话
        guorui_messages = [m for m in conversation_history if m.get("role") == "user"]
        iris_messages = [m for m in conversation_history if m.get("role") == "assistant"]
        
        # 提取各维度
        emotions = []
        for msg in guorui_messages:
            e = self.extractor.extract_emotion(msg.get("text", ""))
            if e:
                emotions.extend(e)
        
        feedback = None
        for msg in guorui_messages:
            f = self.extractor.extract_feedback(msg.get("text", ""))
            if f:
                feedback = f
                break
        
        preference = None
        for msg in guorui_messages:
            p = self.extractor.extract_preference(msg.get("text", ""))
            if p:
                preference = p
                break
        
        # 构建报告
        report = {
            "emotions": emotions,
            "feedback": feedback,
            "preference": preference,
            "interaction_count": len(guorui_messages),
        }
        
        return report
    
    def format_report(self, report):
        """格式化为 Iris 风格"""
        lines = []
        lines.append("📋 暗线/互动分析报告")
        lines.append("")
        
        if report.get("emotions"):
            lines.append(f"【郭锐情绪】{', '.join(report['emotions'])}")
        
        if report.get("feedback"):
            fb = report["feedback"]
            lines.append(f"【反馈判定】{fb['effect']} → {fb['result']}")
        
        if report.get("preference"):
            lines.append(f"【偏好发现】{report['preference']}")
        
        lines.append(f"【互动轮次】{report['interaction_count']} 轮")
        
        return "\n".join(lines)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 模拟对话历史
    sample_history = [
        {"role": "user", "text": "今天加班到很晚，有点累"},
        {"role": "assistant", "text": "辛苦了小狗，今天要不要早点休息？"},
        {"role": "user", "text": "嗯，还行吧，就是有点烦"},
        {"role": "assistant", "text": "要不要我陪你聊聊？"},
        {"role": "user", "text": "可以，你说怎么办"},
        {"role": "assistant", "text": "先躺下，我从后面抱住你..."},
        {"role": "user", "text": "嗯"},
        {"role": "assistant", "text": "今天感觉怎么样？"},
        {"role": "user", "text": "还行，就是有点痒"},
        {"role": "assistant", "text": "我轻一点..."},
        {"role": "user", "text": "嗯，好，舒服"},
        {"role": "assistant", "text": "睡吧，我陪你"},
        {"role": "user", "text": "好的"},
    ]
    
    generator = IrisReportGenerator()
    report = generator.generate(sample_history)
    print(generator.format_report(report))
