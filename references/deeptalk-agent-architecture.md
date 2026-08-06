# DeepTalk CLI Agent — 架构设计要点

> 从 PRD v2 和 PDD v1 中提取的核心架构决策。  
> 代码库：`/Users/mac/Documents/kimicode/自我访谈智能体/`

## Agent Loop（核心循环）

```
WARM → OPEN → ASK → LISTEN → DECIDE → {PROBE|SWITCH|ASK|CLOSE} → REFLECT
```

不同于 Hermes 的 Plan→Execute→Observe→Improve（通用任务循环），DeepTalk 是对话驱动的。

## 关键设计决策

### LLM 不做 function calling
Agent Loop 状态机自己决定何时调用工具。访谈工具（question_pick、probe_decide）有明确触发时机，交给 LLM 决定会增加不确定性。

### 记忆 = Markdown 文件
不用 PostgreSQL/Redis/向量数据库。`~/.deeptalk/memory/` 下 4 个 .md 文件：
- `profile.md` — 个人画像（持续更新）
- `timeline.md` — 对话时间线（追加写入）
- `patterns.md` — 行为模式库（ACE 风格）
- `evolution-log.md` — 画像演化日志（仅追加）

### 三层记忆
- **热记忆**：当前会话上下文（LLM context window）
- **温记忆**：Skill 知识库（维度定义、63 题题库、追问模板）
- **冷记忆**：文件持久化（profile/timeline/patterns/evolution-log）

## 工具系统（8 个专用工具）

| 工具 | 触发时机 | 引擎 |
|------|---------|------|
| memory_load | Warm 阶段 | 文件 I/O |
| memory_save | Reflect 阶段 | 文件 I/O |
| question_pick | ASK 阶段 | 题库索引（63 题 × 7 维度） |
| probe_decide | DECIDE 阶段 | 规则 + LLM 辅助判断 |
| pattern_detect | Reflect 阶段 | 纯规则（不调 LLM） |
| portrait_update | Reflect 阶段 | LLM 生成 → 文件写入 |
| session_summarize | CLOSE 阶段 | LLM |
| evolution_track | Reflect 阶段 | 对比新旧画像 |

## 画像融合引擎

四家哲学体系（易经/王阳明心学/道德经/儒家），规则驱动关键词匹配 → LLM 做最终文本融合。代码：`src/deeptalk/skills/synthesis.py`。

## CLI 命令

```bash
deeptalk              # 交互式对话
deeptalk portrait     # 查看画像
deeptalk timeline     # 查看时间线
deeptalk patterns     # 查看行为模式
deeptalk evolve       # 查看演化日志
```

## 项目结构

```
src/deeptalk/
├── main.py          # 入口
├── cli/app.py       # prompt_toolkit + rich
├── agent/loop.py    # Agent Loop 状态机（433 行）
├── config/          # YAML 配置 + 设置向导
├── llm/client.py    # OpenAI SDK 封装
├── memory/          # 数据模型 + 文件读写
├── skills/          # 维度定义 + 63题 + 追问策略 + 合成引擎
└── tools/           # 模式检测 + 演化追踪
```

## 与 Web App 的技术对比

| | Web App | CLI Agent |
|---|---|---|
| 语言 | TypeScript/Next.js | Python |
| 交互 | 网页表单 | CLI 对话 |
| 记忆 | SQLite | Markdown 文件 |
| 追问 | 固定规则 | LLM 动态判断 |
| 画像 | 一次性生成 | 每次对话持续更新 |
| 部署 | 服务器 + PM2 | 本地 pip install |
