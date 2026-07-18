#!/usr/bin/env python3
"""
gen_profile.py v2 — 从访谈原始数据生成「个人操作手册」结构化画像

与 v1 的关键区别：
- 不再硬编码字典，改为从 data/interviews/ 的原始文件动态读取
- 按「个人操作手册」格式输出（结合 360反馈 + 高管手册 + README 结构）
- 包含：矛盾点前置、行动建议、合作规则、补救机制
- 支持 D7（家庭与身份认同）数据整合

用法:
  python3 scripts/gen_profile.py                    # 生成详细版
  python3 scripts/gen_profile.py --mode condensed   # 生成精简版
  python3 scripts/gen_profile.py --mode all         # 生成两个版本
"""

import json, os, glob, re, sys
from pathlib import Path
from datetime import datetime

DATA = Path(__file__).resolve().parent.parent / "data"
INTERVIEWS = DATA / "interviews"
PROGRESS_FILE = DATA / "interview-progress.json"
OUT = DATA / "profile"
OUT.mkdir(parents=True, exist_ok=True)


# ── 辅助函数 ─────────────────────────────────────────────

def clean_raw(text):
    """清理 raw answer 中的时间戳前缀和格式噪声"""
    if not text:
        return ""
    text = re.sub(r'^\[[^\]]+\]\s*', '', text)
    text = re.sub(r'\*\*时间戳:\*\*\s*\[[^\]]+\]', '', text)
    text = re.sub(r'\n---+\s*$', '', text)
    return text.strip()


def is_empty(raw):
    """判断 raw answer 是否为空或占位符"""
    if not raw or not raw.strip():
        return True
    placeholder = "（旧访谈记录存在，但回答内容为空或格式不符）"
    return raw.strip() == placeholder


def smart_truncate(text, max_len=80):
    """智能截断：在 max_len 内找第一个句号/逗号截断"""
    if len(text) <= max_len:
        return text
    search_range = int(max_len * 0.7)
    for punct in ['。', '；', '，']:
        pos = text.find(punct, search_range, max_len)
        if pos > 0:
            return text[:pos+1]
    pos = text.rfind(' ', search_range, max_len)
    if pos > 0:
        return text[:pos] + '……'
    return text[:max_len] + '……'


# ── 数据读取层 ─────────────────────────────────────────────

def parse_interview(filepath):
    """从单个访谈文件提取结构化数据"""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

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

    raw_match = re.search(r"## Raw answer\n(.+?)(?:\n##|\n---|$)", body, re.DOTALL)
    raw = clean_raw(raw_match.group(1).strip() if raw_match else "")

    cross_ref = []
    cr = fm.get("cross_ref", "[]")
    try:
        cross_ref = json.loads(cr)
    except (json.JSONDecodeError, TypeError):
        pass

    hooks = []
    hook_match = re.search(r"### Cross-dimension hooks\n(.+?)(?:\n###|\n---|$)", body, re.DOTALL)
    if hook_match:
        for line in hook_match.group(1).strip().split("\n"):
            m = re.search(r"\[\[([^\]]+)\]\]", line)
            if m:
                hooks.append(m.group(1))

    tags = []
    tag_match = re.search(r"### Tags\n(.+?)(?:\n---|$)", body, re.DOTALL)
    if tag_match:
        tags = [t.strip().lstrip("#") for t in tag_match.group(1).strip().split() if t.strip()]

    return {
        "dimension": fm.get("dimension", ""),
        "topic": fm.get("topic", ""),
        "question_id": fm.get("question_id", ""),
        "raw": raw,
        "is_empty": is_empty(raw),
        "cross_ref": list(set(cross_ref + hooks)),
        "tags": tags,
    }


def load_all_interviews():
    """加载所有访谈文件"""
    files = sorted(INTERVIEWS.glob("*.md"))
    interviews = []
    for f in files:
        if "progress" in f.name:
            continue
        data = parse_interview(f)
        if data["question_id"]:
            interviews.append(data)
    return interviews


def find_answer(interviews, qid):
    """按 question_id 查找回答，跳过空的"""
    for i in interviews:
        if i["question_id"] == qid and not i["is_empty"]:
            return i["raw"]
    return ""


# ── 内容生成层 ─────────────────────────────────────────────

def generate_section_one_liner(interviews):
    drive = find_answer(interviews, "D4-B3") or "掌控自己的命运"
    strength = find_answer(interviews, "D6-A1")
    growth = find_answer(interviews, "D3-C1")
    parts = []
    if drive:
        parts.append(f"被「{re.sub(r'[。，！？]', '', drive)[:24]}」驱动")
    if strength:
        parts.append(f"擅长{re.sub(r'[。，！？]', '', strength)[:30]}")
    if growth:
        g = re.sub(r'[。，！？]', '', growth)[:30]
        if g:
            parts.append(f"在{g}中加速成长")
    return "，".join(parts) if parts else "暂无数据"


def generate_decision_os(interviews):
    d1a3 = find_answer(interviews, "D1-A3") or ""
    d1b3 = find_answer(interviews, "D1-B3") or ""
    d1a2 = find_answer(interviews, "D1-A2") or ""
    rules = []
    if d1a3:
        rules.append(f"**做决定前的三步自问：** {d1a3}")
    if d1b3:
        rules.append(f"**什么情况下我会忽略数据：** {d1b3}")
        rules.append("**→ 应对规则：** 在做重要决定前，强制找至少一个持反对意见的人讨论，或设置 24 小时冷静期再执行。")
    courage_gap = any(kw in d1a2 for kw in ["勇气","没行动","没有入场"])
    if d1a2 and courage_gap:
        rules.append(f"**风险模式（勇气缺口）：** 看懂了但没行动——{d1a2[:80]}……")
        rules.append("**→ 应对规则：** 当自己说「我看懂了但再等等」时，设置 3 天硬期限。如果 3 天后仍然认为是对的，执行最小投入验证。")
    return rules


def generate_learning_os(interviews):
    d3a1 = find_answer(interviews, "D3-A1") or ""
    d3a3 = find_answer(interviews, "D3-A3") or ""
    d3b1 = find_answer(interviews, "D3-B1") or ""
    d3b3 = find_answer(interviews, "D3-B3") or ""
    items = []
    if d3a1:
        items.append(f"**学习起点：** {d3a1}")
    if d3b1:
        items.append(f"**跨领域迁移：** {d3b1[:100]}……" if len(d3b1) > 100 else f"**跨领域迁移：** {d3b1}")
    if d3b3:
        items.append(f"**能力迁移的关键：** {d3b3[:80]}……" if len(d3b3) > 80 else f"**能力迁移的关键：** {d3b3}")
    if d3a3:
        items.append(f"**愿意为学习放弃什么：** {d3a3}")
    return items


def generate_motivation_profile(interviews):
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
        items.append(f"**真正的驱动力：** {d4b3}")
    if d4a3:
        items.append(f"**什么可以让我放弃高薪/稳定：** {d4a3[:80]}……" if len(d4a3) > 80 else f"**什么可以让我放弃高薪/稳定：** {d4a3}")
    return items


def generate_blindspots(interviews):
    d1b3 = find_answer(interviews, "D1-B3")
    d5a1 = find_answer(interviews, "D5-A1")
    d5a3 = find_answer(interviews, "D5-A3")
    d5c3 = find_answer(interviews, "D5-C3")
    items = []

    _clean = lambda t: re.sub(r'^\[[^\]]+\]\s*', '', t) if t else ""

    if d1b3:
        items.append(f"**过度自信时关掉信息渠道：** {d1b3}")
    if d5a3:
        items.append(f"**自知的 3 个不满意：** {_clean(d5a3)}")
    if d5a1:
        items.append(f"**自我评价偏差：** {_clean(d5a1)}")
    if d5c3:
        items.append(f"**自认为的盲点位置：** {_clean(d5c3)[:80]}……")
    return items


def generate_collaboration_guide(interviews):
    d2a1 = find_answer(interviews, "D2-A1")
    d2a3 = find_answer(interviews, "D2-A3")
    d2b2 = find_answer(interviews, "D2-B2")
    d2c3 = find_answer(interviews, "D2-C3")
    d5b1 = find_answer(interviews, "D5-B1")
    d5b3 = find_answer(interviews, "D5-B3")
    items = []
    _clean = lambda t: re.sub(r'^\[[^\]]+\]\s*', '', t) if t else ""
    if d2c3:
        items.append(f"**沟通偏好：** {d2c3} → 需要对方主动追问细节，不用等我展开。")
    if d2b2:
        items.append(f"**冲突触发点：** {d2b2}")
    if d2a3:
        items.append(f"**建立信任的方式：** {d2a3}")
    if d2a1:
        items.append(f"**我跟人建立信任的过程：** {d2a1}")
    if d5b1:
        items.append(f"**什么情况下我会不想说：** {_clean(d5b1)}")
    if d5b3:
        items.append(f"**我保护自己的方式：** {_clean(d5b3)}")
    return items


def generate_family_identity(interviews):
    d7a1 = find_answer(interviews, "D7-A1") or ""
    d7a2 = find_answer(interviews, "D7-A2") or ""
    d7a3 = find_answer(interviews, "D7-A3") or ""
    d7b2 = find_answer(interviews, "D7-B2") or ""
    d7b3 = find_answer(interviews, "D7-B3") or ""
    d7c1 = find_answer(interviews, "D7-C1") or ""
    d7c2 = find_answer(interviews, "D7-C2") or ""
    d7c3 = find_answer(interviews, "D7-C3") or ""
    items = []
    if d7a1:
        items.append(f"**家庭出身：** {d7a1}")
    if d7a2:
        items.append(f"**父母关系与影响：** {smart_truncate(d7a2, 100)}")
    if d7a3:
        items.append(f"**在我看来，** {d7a3}")
    if d7b2:
        items.append(f"**不想继承的：** {smart_truncate(d7b2, 100)}")
    if d7b3:
        items.append(f"**想要证明的对象：** {d7b3}")
    if d7c1:
        items.append(f"**我的标签：** {d7c1}")
    if d7c2:
        items.append(f"**别人眼中的我 vs 真实的我：** {smart_truncate(d7c2, 80)}")
    if d7c3:
        items.append(f"**不受他人期待时我想成为的人：** {d7c3}")
    return items


def generate_core_contradictions(interviews):
    d4c1 = find_answer(interviews, "D4-C1") or ""
    contradictions = []

    # 矛盾 1: 掌控 vs 稳定
    if d4c1:
        contradictions.append({
            "title": "掌控欲 vs 稳定欲",
            "description": d4c1,
            "battlefield": "每次在「要不要换工作/赛道」时最明显",
            "stop_loss": "如果纠结超过 2 周，两边都放不下。不做重大变动，先小幅验证再决定。"
        })

    # 矛盾 2: 过度自信 vs 知道会盲目
    overconfident = find_answer(interviews, "D1-B3") or ""
    if overconfident:
        contradictions.append({
            "title": "过度自信 vs 知道自己会盲目",
            "description": f"知道过度自信时会忽略数据和他人意见（{smart_truncate(overconfident, 60)}），但无法阻止",
            "battlefield": "做自己擅长领域的决策时",
            "stop_loss": "重要决定必须经过至少一个人挑战你的结论"
        })

    # 矛盾 3: 高标准 vs 孤独
    high_standard = find_answer(interviews, "D2-A1") or ""
    if high_standard:
        contradictions.append({
            "title": "高标准 vs 需要信任关系",
            "description": f"信任标准高，很难遇到志同道合的人（{smart_truncate(high_standard, 60)}）",
            "battlefield": "新环境建立关系时",
            "stop_loss": "接受「大多数人只能陪你走一段路」"
        })

    # 矛盾 4: 勇气缺口
    d1a2 = find_answer(interviews, "D1-A2") or ""
    if d1a2:
        contradictions.append({
            "title": "认知深度 vs 行动勇气",
            "description": f"看懂了但不敢入场（{smart_truncate(d1a2, 40)}）。模式一致：特警考试也是这样。",
            "battlefield": "面对高不确定性但高回报的机会时",
            "stop_loss": "建立「最小勇气规则」：如果一件事你连续想 3 天，执行最小投入"
        })

    # 矛盾 5: 家庭身份冲突
    d7a2 = find_answer(interviews, "D7-A2") or ""
    d7a3 = find_answer(interviews, "D7-A3") or ""
    d7c2 = find_answer(interviews, "D7-C2") or ""
    if "弱势" in d7a2 and "性格" in d7a3:
        contradictions.append({
            "title": "用父亲的性格活着，用母亲的标准审着自己",
            "description": f"性格像父亲（弱势、温和），但想法像母亲（强势、结果导向）。认真做事没结果时，心里的声音是「不能像我爸那样」（{smart_truncate(d7c2, 50)}）",
            "battlefield": "认真做了一件事但没出结果时",
            "stop_loss": "区分「做事」和「证明自己」。没有结果不代表你不行。"
        })

    # 矛盾 6: 证明给别人看 vs 为自己活
    d7b3 = find_answer(interviews, "D7-B3") or ""
    d7c3 = find_answer(interviews, "D7-C3") or ""
    if d7b3 and "自由" in d7c3:
        contradictions.append({
            "title": "证明给别人看 vs 为自己活",
            "description": f"不需要考虑他人期待时，你想成为掌控自己命运的人（{smart_truncate(d7c3, 40)}）。但现实中你在努力向他人证明能力（{smart_truncate(d7b3, 40)}）。",
            "battlefield": "选择工作/项目时：选能证明自己的，还是选能让自己掌控人生的？",
            "stop_loss": "每三个月问自己一次：你现在做的事，在通往自由的路上，还是在远离它？"
        })

    return contradictions


def generate_final_reminder(interviews):
    d4b3 = find_answer(interviews, "D4-B3") or ""
    d4c1 = find_answer(interviews, "D4-C1") or ""
    if "掌控" in d4b3 and "稳定" in d4c1:
        return "你知道你要掌控，也知道你想要稳定。两者冲突的时候，记住：你曾经的选择都是「做了再说」。"
    return "暂无"


# ── 渲染层 ─────────────────────────────────────────────

def render_profile(interviews, mode="detailed"):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    completed_count = len(interviews)

    one_liner = generate_section_one_liner(interviews)
    d3c2 = find_answer(interviews, "D3-C2") or ""
    decision_os = generate_decision_os(interviews)
    learning_os = generate_learning_os(interviews)
    motivation = generate_motivation_profile(interviews)
    blindspots = generate_blindspots(interviews)
    collab = generate_collaboration_guide(interviews)
    family = generate_family_identity(interviews)
    contradictions = generate_core_contradictions(interviews)
    reminder = generate_final_reminder(interviews)

    lines = []
    lines.append("---")
    lines.append(f"generated_at: {today}")
    lines.append(f"total_questions: {completed_count}")
    lines.append("type: personal-operating-manual")
    lines.append("status: generated")
    lines.append("---\n")
    lines.append("# 个人操作手册\n")
    lines.append(f"基于 {completed_count} 条深度自我访谈生成。\n")
    lines.append("## 一句话说明\n")
    lines.append(f"{one_liner}\n")

    if family:
        lines.append("## 家庭出身与自我认同\n")
        for item in family:
            lines.append(f"- {item}")
        lines.append("")

    if d3c2:
        lines.append("## 当前焦点\n")
        lines.append(f"{d3c2}\n")

    lines.append("## 我的决策操作系统\n")
    if decision_os:
        for item in decision_os:
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## 我的学习模式\n")
    if learning_os:
        for item in learning_os:
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## 我的激励密码\n")
    if motivation:
        for item in motivation:
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## 已知盲点与补救机制\n")
    lines.append("> 这些是访谈中自己识别出来的模式。知道不等于能改，所以设置了补救规则。\n")
    if blindspots:
        for item in blindspots:
            lines.append(f"- {item}")
    lines.append("")

    if mode == "detailed" and collab:
        lines.append("## 跟我合作的规则\n")
        for item in collab:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 核心矛盾\n")
    lines.append("> 矛盾不是「问题」——是你的操作系统里同时运行着两套逻辑。意识到它们，比消除它们重要。\n")
    for c in contradictions:
        lines.append(f"### {c['title']}\n")
        lines.append(f"{c['description']}\n")
        lines.append(f"- **冲突场景：** {c.get('battlefield', '')}")
        lines.append(f"- **止损规则：** {c.get('stop_loss', '')}\n")

    if reminder:
        lines.append("---\n")
        lines.append(f"*{reminder}*\n")

    return "\n".join(lines)


def write_profile(content, mode="detailed"):
    today = datetime.now().strftime("%Y-%m-%d")
    suffix = "" if mode == "detailed" else "--condensed"
    out_path = OUT / f"{today}--personal-operating-manual{suffix}.md"
    with open(out_path, "w", encoding='utf-8') as f:
        f.write(content)
    return out_path


# ── 主入口 ─────────────────────────────────────────────

def main():
    mode = "detailed"
    if len(sys.argv) > 2 and sys.argv[1] == "--mode":
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


if __name__ == "__main__":
    main()
