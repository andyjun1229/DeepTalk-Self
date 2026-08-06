#!/usr/bin/env python3
"""
gen_profile.py v2 — 从访谈原始数据生成「个人操作手册」结构化画像

与 v1 的关键区别：
- 不再硬编码字典，改为从 data/interviews/ 的原始文件动态读取
- 按「个人操作手册」格式输出（结合 360反馈 + 高管手册 + README 结构）
- 包含：矛盾点前置、行动建议、合作规则、补救机制
- 支持输出个人版（detailed）和公开版（condensed）

用法:
  python3 gen_profile.py                    # 生成详细版（个人操作手册）
  python3 gen_profile.py --mode condensed   # 生成精简版
  python3 gen_profile.py --mode all         # 生成两个版本
"""

import json, os, glob, re, sys
from pathlib import Path
from datetime import datetime

DATA = Path(__file__).parent.parent / "data"
INTERVIEWS = DATA / "interviews"
PROGRESS_FILE = DATA / "interview-progress.json"
OUT = DATA / "profile"
OUT.mkdir(parents=True, exist_ok=True)


# ── 辅助函数 ─────────────────────────────────────────────

def clean_raw(text):
    """清理 raw answer 中的时间戳前缀和格式噪声"""
    if not text:
        return ""
    # 去掉行首时间戳: [Mon 2026-06-22 14:29 GMT+8]
    text = re.sub(r'^\[[^\]]+\]\s*', '', text)
    # 去掉末尾的 **时间戳:** 行
    text = re.sub(r'\*\*时间戳:\*\*\s*\[[^\]]+\]', '', text)
    # 去掉末尾多余的 ---
    text = re.sub(r'\n---+\s*$', '', text)
    return text.strip()


def is_empty(raw):
    """判断 raw answer 是否为空或占位符"""
    if not raw or not raw.strip():
        return True
    placeholder = "（旧访谈记录存在，但回答内容为空或格式不符）"
    return raw.strip() == placeholder


# ── 数据读取层 ─────────────────────────────────────────────

def parse_interview(filepath):
    """从单个访谈文件提取结构化数据"""
    with open(filepath) as f:
        content = f.read()

    # 解析 frontmatter
    fm = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            body = parts[2]
        else:
            body = content
    else:
        body = content

    # 提取 raw answer 部分
    raw_match = re.search(r"## Raw answer\n(.+?)(?:\n##|\n---|$)", body, re.DOTALL)
    raw = clean_raw(raw_match.group(1).strip() if raw_match else "")

    # 提取 cross_ref
    cross_ref = []
    # 从 frontmatter 的 cross_ref 字段解析
    cr = fm.get("cross_ref", "[]")
    try:
        cross_ref = json.loads(cr)
    except (json.JSONDecodeError, TypeError):
        pass

    # 从 body 中提取 cross-dimension hooks
    hooks = []
    hook_match = re.search(r"### Cross-dimension hooks\n(.+?)(?:\n###|\n---|$)", body, re.DOTALL)
    if hook_match:
        for line in hook_match.group(1).strip().split("\n"):
            m = re.search(r"\[\[([^\]]+)\]\]", line)
            if m:
                hooks.append(m.group(1))

    # 提取 tags
    tags = []
    tag_match = re.search(r"### Tags\n(.+?)(?:\n---|$)", body, re.DOTALL)
    if tag_match:
        tags = [t.strip().lstrip("#") for t in tag_match.group(1).strip().split() if t.strip()]

    # 提取 behavioral facts
    facts = []
    fact_match = re.search(r"### Behavioral facts\n(.+?)(?:\n###|\n---|$)", body, re.DOTALL)
    if fact_match:
        for line in fact_match.group(1).strip().split("\n"):
            m = re.search(r"-\s*(Fact \d+:?\s*)?(.+)", line)
            if m:
                facts.append(m.group(2).strip())

    # 提取 claims vs behavior gap
    claim_text = ""
    gap_text = ""
    gap_match = re.search(r"### Claims vs behavior\n(.+?)(?:\n###|\n---|$)", body, re.DOTALL)
    if gap_match:
        for line in gap_match.group(1).strip().split("\n"):
            if line.startswith("- Claim:"):
                claim_text = line.replace("- Claim:", "").strip().strip('"').strip("'")
            if line.startswith("- Gap:"):
                gap_text = line.replace("- Gap:", "").strip().strip('"').strip("'")

    return {
        "dimension": fm.get("dimension", ""),
        "topic": fm.get("topic", ""),
        "question_id": fm.get("question_id", ""),
        "raw": raw,
        "is_empty": is_empty(raw),
        "cross_ref": list(set(cross_ref + hooks)),
        "tags": tags,
        "facts": facts,
        "claim": claim_text,
        "gap": gap_text,
    }


def load_all_interviews():
    """加载所有访谈文件"""
    files = sorted(INTERVIEWS.glob("*.md"))
    interviews = []
    for f in files:
        # 跳过进度文件
        if "progress" in f.name:
            continue
        data = parse_interview(f)
        if data["question_id"]:
            interviews.append(data)
    return interviews


def group_by_dimension(interviews):
    """按维度分组"""
    dims = {}
    for i in interviews:
        dim = i["dimension"]
        if dim not in dims:
            dims[dim] = []
        dims[dim].append(i)
    return dims


# ── 内容生成层 ─────────────────────────────────────────────

def get_tags_for_dimension(interviews, dim):
    """获取某个维度的所有标签"""
    tags = set()
    for i in interviews:
        if i["dimension"] == dim:
            tags.update(i["tags"])
    return sorted(tags)


def find_answer(interviews, qid):
    """按 question_id 查找回答，跳过空的"""
    for i in interviews:
        if i["question_id"] == qid and not i["is_empty"]:
            return i["raw"]
    return ""


def generate_section_one_liner(interviews):
    """一句话说明：跨维度综合提取"""
    drive = find_answer(interviews, "D4-B3") or "掌控自己的命运"
    strength = find_answer(interviews, "D6-A1")
    growth = find_answer(interviews, "D3-C1")

    parts = []
    if drive:
        drive_clean = re.sub(r'[。，！？\.,!?].*', '', drive)[:24]
        parts.append(f"被「{drive_clean}」驱动")
    if strength:
        strength_clean = re.sub(r'[。，！？\.,!?].*', '', strength)[:30]
        parts.append(f"擅长{strength_clean}")
    if growth:
        growth_clean = re.sub(r'[。，！？\.,!?].*', '', growth)[:30]
        growth_clean = re.sub(r'^[在在]{1,2}', '', growth_clean)  # 去掉开头的"在"（避免"在在XXX中"）
        if growth_clean:
            parts.append(f"在{growth_clean}中加速成长")

    return "，".join(parts) if parts else "暂无数据"


def generate_decision_os(interviews):
    """生成决策操作系统章节"""
    # D1-A1 决策框架
    d1a1 = find_answer(interviews, "D1-A1") or ""
    # D1-A3 决策前三问
    d1a3 = find_answer(interviews, "D1-A3") or ""
    # D1-B3 忽略数据的情况
    d1b3 = find_answer(interviews, "D1-B3") or ""
    # D1-A2 后悔模式
    d1a2 = find_answer(interviews, "D1-A2") or ""

    # 提取消极 vs 积极行动模式
    courage_gap = False
    all_in_compensation = False
    if "勇气" in d1a2 or "没行动" in d1a2 or "没有入场" in d1a2:
        courage_gap = True
    if "All In" in d1a2 or "all in" in d1a2 or "补偿" in d1a2:
        all_in_compensation = True

    rules = []
    if d1a3:
        rules.append(f"**做决定前的三步自问：** {d1a3}")
    if d1b3:
        rules.append(f"**什么情况下我会忽略数据：** {d1b3}")
        rules.append(f"**→ 应对规则：** 在做重要决定前，强制找至少一个持反对意见的人讨论，或设置 24 小时冷静期再执行。")
    if courage_gap:
        rules.append(f"**风险模式（勇气缺口）：** 看懂了但没行动——{d1a2[:80]}……")
        rules.append(f"**→ 应对规则：** 当自己说「我看懂了但再等等」时，设置 3 天硬期限。如果 3 天后仍然认为是对的，必须执行最小投入验证。")

    return rules


def generate_learning_os(interviews):
    """生成学习模式章节"""
    d3a1 = find_answer(interviews, "D3-A1") or ""
    d3a3 = find_answer(interviews, "D3-A3") or ""
    d3b1 = find_answer(interviews, "D3-B1") or ""
    d3b3 = find_answer(interviews, "D3-B3") or ""
    d3c1 = find_answer(interviews, "D3-C1") or ""
    d3c2 = find_answer(interviews, "D3-C2") or ""

    items = []
    if d3a1:
        items.append(f"**学习起点：** {d3a1}")
    if d3b1:
        items.append(f"**跨领域迁移：** {d3b1[:100]}……" if len(d3b1) > 100 else f"**跨领域迁移：** {d3b1}")
    if d3b3:
        items.append(f"**能力迁移的关键认知：** {d3b3[:80]}……" if len(d3b3) > 80 else f"**能力迁移的关键：** {d3b3}")
    if d3a3:
        items.append(f"**愿意为学习放弃什么：** {d3a3}")

    return items


def generate_motivation_profile(interviews):
    """生成激励密码章节"""
    d4b1 = find_answer(interviews, "D4-B1") or ""
    d4b3 = find_answer(interviews, "D4-B3") or ""
    d4a3 = find_answer(interviews, "D4-A3") or ""
    d4a1 = find_answer(interviews, "D4-A1") or ""

    items = []
    if d4a1:
        items.append(f"**核心价值排序（永远选的那个）：** {d4a1}")
    if d4b1:
        items.append(f"**什么让我觉得「今天没白过」：** {d4b1}")
    if d4b3:
        items.append(f"**真正的驱动力（不是「应该」，是「真正推动」）：** {d4b3}")
    if d4a3:
        items.append(f"**什么可以让我放弃高薪/稳定：** {d4a3[:80]}……" if len(d4a3) > 80 else f"**什么可以让我放弃高薪/稳定：** {d4a3}")

    return items


def generate_blindspots(interviews):
    """生成盲点章节（已知的 + 补救机制）"""
    items = []

    d1b3 = find_answer(interviews, "D1-B3")
    d5a1 = find_answer(interviews, "D5-A1")
    d5a3 = find_answer(interviews, "D5-A3")
    d5c3 = find_answer(interviews, "D5-C3")

    if d1b3:
        items.append(f"**过度自信时关掉信息渠道：** {d1b3}")
    if d5a3:
        # 清理时间戳前缀
        d5a3_clean = re.sub(r'^\[[^\]]+\]\s*', '', d5a3)
        items.append(f"**自知的 3 个不满意：** {d5a3_clean}")
    if d5a1:
        d5a1_clean = re.sub(r'^\[[^\]]+\]\s*', '', d5a1)
        items.append(f"**自我评价偏差：** {d5a1_clean}")
    if d5c3:
        d5c3_clean = re.sub(r'^\[[^\]]+\]\s*', '', d5c3)
        items.append(f"**自认为的盲点位置：** {d5c3_clean[:80]}……" if len(d5c3_clean) > 80 else f"**自认为的盲点位置：** {d5c3_clean}")

    return items


def generate_collaboration_guide(interviews):
    """生成合作规则（README 风格）"""
    d2a1 = find_answer(interviews, "D2-A1")
    d2a3 = find_answer(interviews, "D2-A3")
    d2b2 = find_answer(interviews, "D2-B2")
    d2c3 = find_answer(interviews, "D2-C3")
    d5b1 = find_answer(interviews, "D5-B1")
    d5b3 = find_answer(interviews, "D5-B3")

    items = []
    if d2c3:
        items.append(f"**沟通偏好：** {d2c3} → 需要对方主动追问细节，不用等我展开。")
    if d2b2:
        items.append(f"**冲突触发点：** {d2b2}")
    if d2a3:
        items.append(f"**建立信任的方式（对方做这些更容易获得信任）：** {d2a3}")
    if d2a1:
        items.append(f"**我跟人建立信任的过程：** {d2a1}")
    if d5b1:
        d5b1_clean = re.sub(r'^\[[^\]]+\]\s*', '', d5b1)
        items.append(f"**什么情况下我会不想说：** {d5b1_clean}")
    if d5b3:
        d5b3_clean = re.sub(r'^\[[^\]]+\]\s*', '', d5b3)
        items.append(f"**我保护自己的方式：** {d5b3_clean}")

    return items


def smart_truncate(text, max_len=80):
    """智能截断：在 max_len 内找第一个句号/逗号/分号截断，否则在 max_len 处截"""
    if len(text) <= max_len:
        return text
    # 尝试在前 2/3 的范围内找自然断点
    search_range = int(max_len * 0.7)
    for punct in ['。', '；', '，']:
        pos = text.find(punct, search_range, max_len)
        if pos > 0:
            return text[:pos+1]
    # 找空格
    pos = text.rfind(' ', search_range, max_len)
    if pos > 0:
        return text[:pos] + '……'
    return text[:max_len] + '……'


def generate_core_contradictions(interviews):
    """
    生成核心矛盾章节。
    通过 cross_ref 关联和数据交叉分析，找出跨维度的矛盾模式。
    """
    # 从 D4-C1 找核心矛盾
    d4c1 = find_answer(interviews, "D4-C1") or ""

    contradictions = []

    # 矛盾 1: 掌控 vs 稳定（从 D4-C1 + D4-B3 交叉）
    if d4c1:
        contradictions.append({
            "title": "掌控欲 vs 稳定欲",
            "description": d4c1,
            "source": "D4-C1 价值观矛盾",
            "battlefield": "每次在「要不要换工作/赛道」时最明显",
            "stop_loss": "如果纠结超过 2 周，说明两边都放不下。此时不做重大变动，先小幅验证再决定。"
        })

    # 矛盾 2: 过度自信 vs 知道会盲目（D1-B3 + D5-A1 + D5-A3 交叉）
    overconfident = find_answer(interviews, "D1-B3") or ""
    blind_aware = find_answer(interviews, "D5-A1") or ""
    if overconfident:
        contradictions.append({
            "title": "过度自信 vs 知道自己会盲目",
            "description": f"知道过度自信时会忽略数据和他人意见（{smart_truncate(overconfident, 60)}），但无法阻止",
            "source": "D1-B3 × D5-A1 交叉",
            "battlefield": "做自己擅长领域的决策时",
            "stop_loss": "重要决定必须经过至少一个人挑战你的结论"
        })

    # 矛盾 3: 高标准 vs 孤独（D2-A1 提到孤独 + D5-A3 提到标准）
    high_standard = find_answer(interviews, "D2-A1") or ""
    if high_standard:
        contradictions.append({
            "title": "高标准 vs 需要信任关系",
            "description": f"信任标准高，很难遇到志同道合的人（{smart_truncate(high_standard, 60)}）",
            "source": "D2-A1 × D5-A3",
            "battlefield": "新环境建立关系时",
            "stop_loss": "意识到标准高不等于需要降低标准，而是接受「大多数人只能陪你走一段路」"
        })

    # 矛盾 4: 勇气缺口（D1-A2 + D1-C1）
    d1a2 = find_answer(interviews, "D1-A2") or ""
    d1c1 = find_answer(interviews, "D1-C1") or ""
    courage_text = smart_truncate(d1a2, 40) if d1a2 else ""
    if d1a2 or d1c1:
        contradictions.append({
            "title": "认知深度 vs 行动勇气",
            "description": f"看懂了但不敢入场（{courage_text}）。模式一致：特警考试也是这样。",
            "source": "D1-A2 × D1-C1",
            "battlefield": "面对高不确定性但高回报的机会时",
            "stop_loss": "建立「最小勇气规则」：如果一件事你连续想 3 天，执行最小投入（不用 All In，但要入场）"
        })

    # 矛盾 5: 家庭身份冲突（D7 数据衍生）
    d7a2 = find_answer(interviews, "D7-A2") or ""
    d7a3 = find_answer(interviews, "D7-A3") or ""
    d7b2 = find_answer(interviews, "D7-B2") or ""
    d7b3 = find_answer(interviews, "D7-B3") or ""
    d7c2 = find_answer(interviews, "D7-C2") or ""
    d7c3 = find_answer(interviews, "D7-C3") or ""

    if "弱势" in d7a2 and "性格" in d7a3 and "想法" in d7a3:
        contradictions.append({
            "title": "用父亲的性格活着，用母亲的标准审着自己",
            "description": f"性格像父亲（弱势、温和、被热爱牵引），但想法像母亲（强势、结果导向、评价标准明确）。认真做事没结果时，心里的声音是「不能像我爸那样」——这声音来自教导员，来自爱人，来自内化了的母亲的标准。（{smart_truncate(d7c2, 50)}）",
            "source": "D7-A2 × D7-A3 × D7-C2",
            "battlefield": "认真做了一件事但没出结果时——同时承受失败的挫败 + 被否定的恐惧",
            "stop_loss": f"区分「做事」和「证明自己」。没有结果不代表你不行——不代表你像你爸。把「做成了才证明我有能力」改成「我做这件事本身就是能力」。"
        })

    # 矛盾 6: 证明给别人看 vs 想要自由（D7-B3 × D7-C3）
    if d7b3 and d7c3 and ("自由" in d7c3 or "掌控" in d7c3):
        contradictions.append({
            "title": "证明给别人看 vs 为自己活",
            "description": f"不需要考虑他人期待时，你想成为掌控自己命运的人（{smart_truncate(d7c3, 40)}）。但现实中你却在努力向爱人和外界证明能力（{smart_truncate(d7b3, 40)}）。",
            "source": "D7-B3 × D7-C3",
            "battlefield": "选择工作/项目时：是选能证明自己的，还是选能让自己掌控人生的？",
            "stop_loss": "每三个月问自己一次：你现在做的事情，是在通往自由的路上，还是在远离它？"
        })

    return contradictions


def generate_family_identity(interviews):
    """从 D7 数据生成家庭与身份认同章节"""
    d7a1 = find_answer(interviews, "D7-A1") or ""
    d7a2 = find_answer(interviews, "D7-A2") or ""
    d7a3 = find_answer(interviews, "D7-A3") or ""
    d7b1 = find_answer(interviews, "D7-B1") or ""
    d7b2 = find_answer(interviews, "D7-B2") or ""
    d7b3 = find_answer(interviews, "D7-B3") or ""
    d7c1 = find_answer(interviews, "D7-C1") or ""
    d7c2 = find_answer(interviews, "D7-C2") or ""
    d7c3 = find_answer(interviews, "D7-C3") or ""

    items = []

    # 原生家庭结构
    if d7a1:
        items.append(f"**家庭出身：** {d7a1}")

    # 父母关系
    if d7a2:
        d7a2_short = smart_truncate(d7a2, 100)
        items.append(f"**父母关系与影响：** {d7a2_short}")

    # 性格来源
    if d7a3:
        items.append(f"**在我看来，** {d7a3}")

    # 处事方式
    if d7b2:
        d7b2_short = smart_truncate(d7b2, 100)
        items.append(f"**不想继承的：** {d7b2_short}")

    # 证明给谁看
    if d7b3:
        items.append(f"**想要证明的对象：** {d7b3}")

    # 标签认同
    if d7c1:
        items.append(f"**我的标签：** {d7c1}")

    # 自我认知差异
    if d7c2:
        d7c2_short = smart_truncate(d7c2, 80)
        items.append(f"**别人眼中的我 vs 真实的我：** {d7c2_short}")

    # 终极追求
    if d7c3:
        items.append(f"**不受他人期待时我想成为的人：** {d7c3}")

    return items


def generate_achievement_patterns(interviews):
    """生成成就与贡献感章节"""
    d6c1 = find_answer(interviews, "D6-C1") or ""
    d6c2 = find_answer(interviews, "D6-C2") or ""

    items = []
    if d6c1:
        items.append(f"**最自豪的事：** {d6c1}")
    if d6c2:
        items.append(f"**什么时候感受到贡献：** {d6c2}")
    return items
def generate_final_reminder(interviews):
    d4b3 = find_answer(interviews, "D4-B3") or ""
    d4c1 = find_answer(interviews, "D4-C1") or ""

    if "掌控" in d4b3 and "稳定" in d4c1:
        return "你知道你要掌控，也知道你想要稳定。两者冲突的时候，记住：你曾经的选择都是「做了再说」。"
    return "暂无"


def generate_work_preferences(interviews):
    """生成工作偏好章节"""
    d6b1 = find_answer(interviews, "D6-B1")
    d6b2 = find_answer(interviews, "D6-B2")
    d6b3 = find_answer(interviews, "D6-B3")
    d6a3 = find_answer(interviews, "D6-A3")

    items = []
    if d6b1:
        items.append(f"**独立 vs 团队：** {d6b1}")
    if d6b2:
        items.append(f"**舒适区 vs 不舒适区：** {d6b2}")
    if d6b3:
        items.append(f"**压力反应：** {d6b3}")
    if d6a3:
        items.append(f"**最高效的工作状态：** {d6a3}")

    return items


# ── 输出层 ─────────────────────────────────────────────

def render_profile(interviews, mode="detailed"):
    """生成完整画像内容"""
    dims = group_by_dimension(interviews)
    completed_count = len(interviews)
    dim_count = len([d for d in dims.values() if d])

    today = datetime.now().strftime("%Y-%m-%d")
    one_liner = generate_section_one_liner(interviews)
    decision_os = generate_decision_os(interviews)
    learning_os = generate_learning_os(interviews)
    motivation = generate_motivation_profile(interviews)
    blindspots = generate_blindspots(interviews)
    collab = generate_collaboration_guide(interviews)
    contradictions = generate_core_contradictions(interviews)
    family_identity = generate_family_identity(interviews)
    achievement = generate_achievement_patterns(interviews)
    reminder = generate_final_reminder(interviews)
    work_prefs = generate_work_preferences(interviews)

    # D3-C2 当前焦点
    d3c2 = find_answer(interviews, "D3-C2") or ""
    # D6-C1 成就事件
    d6c1 = find_answer(interviews, "D6-C1") or ""
    # D6-C2 贡献感
    d6c2 = find_answer(interviews, "D6-C2") or ""

    lines = []
    lines.append("---")
    lines.append(f"generated_at: {today} {datetime.now().strftime('%H:%M')}")
    lines.append(f"total_questions: {completed_count}")
    lines.append("type: personal-operating-manual")
    lines.append("status: generated")
    lines.append("---")
    lines.append("")
    lines.append("# 个人操作手册")
    lines.append("")
    lines.append(f"基于 {completed_count} 题深度自我访谈（{max(1,dim_count)} 个维度）生成。")
    lines.append("这份报告不是心理画像——是**一个可执行的理解自己的手册**。")
    lines.append("")

    # ── 一句话说明 ──
    lines.append("## 一句话说明")
    lines.append("")
    lines.append(one_liner)
    lines.append("")

    # ── 家庭与身份认同（D7 新增）──
    if family_identity:
        lines.append("## 家庭出身与自我认同")
        lines.append("")
        for item in family_identity:
            lines.append(f"- {item}")
        lines.append("")

    # ── 当前焦点 ──
    if d3c2:
        lines.append("## 当前焦点")
        lines.append("")
        if mode == "detailed":
            lines.append(f"{d3c2}")
        else:
            lines.append(f"{d3c2[:100]}……")
        lines.append("")

    # ── 决策操作系统 ──
    lines.append("## 我的决策操作系统")
    lines.append("")
    if decision_os:
        for item in decision_os:
            lines.append(f"- {item}")
    lines.append("")

    # ── 学习模式 ──
    lines.append("## 我的学习模式")
    lines.append("")
    if learning_os:
        for item in learning_os:
            lines.append(f"- {item}")
    lines.append("")

    # ── 激励密码 ──
    lines.append("## 我的激励密码")
    lines.append("")
    if motivation:
        for item in motivation:
            lines.append(f"- {item}")
    lines.append("")

    # ── 工作偏好 ──
    if work_prefs:
        lines.append("## 工作方式与偏好")
        lines.append("")
        for item in work_prefs:
            lines.append(f"- {item}")
        lines.append("")

    # ── 盲点（已知的 + 补救机制）──
    lines.append("## 已知盲点与补救机制")
    lines.append("")
    lines.append("> 这些是访谈中自己识别出来的模式。知道不等于能改，所以设置了补救规则。")
    lines.append("")
    if blindspots:
        for item in blindspots:
            lines.append(f"- {item}")
    lines.append("")

    # ── 跟「我」这种人合作的规则 ──
    if mode == "detailed":
        lines.append("## 跟我合作的规则（给同事/合作伙伴的说明书）")
        lines.append("")
        if collab:
            for item in collab:
                lines.append(f"- {item}")
        lines.append("")

    # ── 核心矛盾（最重要的部分）──
    lines.append("## 核心矛盾")
    lines.append("")
    lines.append("> 这里的矛盾不是「问题」——是你的操作系统里同时运行着两套逻辑。意识到它们，比消除它们重要。")
    lines.append("")
    for c in contradictions:
        lines.append(f"### {c['title']}")
        lines.append("")
        lines.append(f"{c['description']}")
        lines.append("")
        lines.append(f"- **冲突场景：** {c.get('battlefield', '')}")
        lines.append(f"- **止损规则：** {c.get('stop_loss', '')}")
        lines.append("")

    # ── 成就规律 ──
    if achievement and mode == "detailed":
        lines.append("## 成就与贡献感")
        lines.append("")
        for ap in achievement:
            lines.append(f"- {ap}")
        lines.append("")

    # ── 一句话提醒 ──
    if reminder:
        lines.append("---")
        lines.append("")
        lines.append(f"*{reminder}*")
        lines.append("")

    return "\n".join(lines)


def write_profile(content, mode="detailed"):
    """写入画像文件"""
    today = datetime.now().strftime("%Y-%m-%d")
    suffix = "" if mode == "detailed" else "--condensed"
    out_path = OUT / f"{today}--personal-operating-manual{suffix}.md"
    with open(out_path, "w") as f:
        f.write(content)
    return out_path


# ── 主入口 ─────────────────────────────────────────────

def main():
    mode = "detailed"
    if len(sys.argv) > 1:
        if sys.argv[1] == "--mode":
            if len(sys.argv) > 2:
                mode = sys.argv[2]

    interviews = load_all_interviews()
    if not interviews:
        print("✗ 没有找到访谈数据。先完成访谈再生成画像。")
        sys.exit(1)

    print(f"✓ 加载了 {len(interviews)} 条访谈回答")

    if mode in ("detailed", "all"):
        content = render_profile(interviews, "detailed")
        path = write_profile(content, "detailed")
        print(f"✓ 详细版画像已生成: {path}")

    if mode in ("condensed", "all"):
        content = render_profile(interviews, "condensed")
        path = write_profile(content, "condensed")
        print(f"✓ 精简版画像已生成: {path}")

    if mode not in ("detailed", "condensed", "all"):
        print(f"✗ 未知模式: {mode}。支持: detailed, condensed, all")
        sys.exit(1)


if __name__ == "__main__":
    main()
