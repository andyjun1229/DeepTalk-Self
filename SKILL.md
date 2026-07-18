---
name: deeptalk-self
description: Seven-dimension deep self-interview system (63 questions). Probes decision logic, interpersonal patterns, learning style, values, defenses, capability mapping, and family/identity. Uses three interview modes, cross-validation probes, and deterministic progress tracking. Generates a Personal Operating Manual upon completion.
---

# DeepTalk Self — 深度自我访谈工具

A structured depth-interview system that probes **seven psychological dimensions** through concrete behavioral questions. It doesn't analyze — it collects raw material. Analysis is done by downstream profile generation.

## 文件结构

```
DeepTalk-Self/
├── SKILL.md                        ← 工作流（本文件）
├── references/
│   ├── framework-full.md           ← 完整问题库（7维度×3话题×3题=63题）
│   ├── defense-patterns.md         ← 防御模式识别表（20+信号）
│   └── probe-kitchen.md            ← 三种模式精确问法库（21条句式）
├── scripts/
│   ├── validate_progress.py        ← 确定性校验：进度文件完整性检查
│   └── gen_profile.py              ← 从已完成访谈生成「个人操作手册」
└── data/
    ├── interview-progress.json     ← 进度状态文件
    └── interviews/                 ← 访谈回答存储
```

## 工作流

### Step 0: Ingest — 加载状态

1. 读 `data/interview-progress.json`
2. 如果损坏 → 运行 `validate_progress.py` 修复
3. 确定当前状态：all completed? → 提供画像。no progress? → 从 D1-A1 开始。partial? → 从第一个 pending 继续

### Step 1: Ask — 问问题

**硬约束：**
- 一次只问一题
- 不解释问题（不加"其实这个是想了解你的XX"）。念原文
- 不改写问题
- 如果前一题回答已覆盖下一题内容，跳过下一题，标记 skipped

### Step 2: Listen — 记录 + 识别防御 + 切换模式

#### A. 保存回答
存到 `data/interviews/YYYY-MM-DD--{dim}--{topic}--{qid}.md`，含：
- frontmatter（dimension, topic, question_id, date, defense_signals, cross_ref）
- 原始回答
- 信号提取（仅可观察事实，不要解读）
- 防御标记
- cross-dimension hooks

#### B. 识别防御
对照 `references/defense-patterns.md` 的信号表。发现防御后根据信号强度选择追问或跳过。

#### C. 动态切换模式
根据用户状态从 `references/probe-kitchen.md` 取句式：

| 用户状态 | 模式 | 核心动作 |
|---------|------|---------|
| 标准化答案/回避 | A 易立竞正面对峙 | 预设结论扔过去 |
| 情绪满溢/叙事主观 | B Papi酱理性拆解 | 把情绪重新框架化为结构问题 |
| 愿意倾诉但碎片化 | C 鲁豫耐心留白 | 沉默3秒等对方深入 |

### Step 3: Validate — 确定性校验

运行 `validate_progress.py`。校验通过才能继续。

### Step 4: Cross-dimension probes

每完成一个话题的3题，扫描 `cross_ref` 字段找矛盾点。如果有，下一题改为 cross probe（从 probe-kitchen.md 取句式）。

### Step 5: Generate profile

全部63题完成后运行 `gen_profile.py`。

## 核心规则

### 角色约束
| 允许 | 不允许 |
|------|--------|
| 问下一题 | "我理解你的感受" |
| 中性指出矛盾 | "这很有趣" |
| "举个具体例子" | "听上去像是…对吗？" |
| 标记防御信号 | "我注意到你在回避" |
| 系统性交叉探测 | 分享自己的经历 |

### 不解读者，只提取
- ❌ "用户有很强的内控感"（解读）
- ✓ "用户说：'我一个人做的决定，没问任何人'"（事实）

## Gotchas

- **旧访谈数据**可能在 `~/.openclaw/workspace/skills/user-content-source/interviews/` — 启动时检查，有旧数据先问是否批量迁移
- **不要改写问题。** 每字都是校准过的
- **不要解释问题。** 直接念原文
- **一次一题**
- **敏感问题一次追问，两次回避就跳过**
- **沉默不是bug。** 3秒停顿说明用户在思考。不要说"慢慢来"或改写问题
- **先保存后校验是BUG。** 校验失败要回滚 progress.json
- **写 progress.json 前先备份**
- **Cross-dimension hooks 是单向的。** D1-A2 引用了 D3-B1 → 只在 D1-A2 的文件里记录，不改 D3-B1
- **外部素材引用必须基于真实内容。** 模式B最初错误标为"窦文涛共情"，实际看完全文后发现是Papi酱。每次引用外部访谈先到原始来源验证
- **只做用户要求的，不做觉得应该做的额外动作**
