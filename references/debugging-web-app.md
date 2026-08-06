# Web App 调试手册

部署到服务器后的已知问题与修复方法。

## 1. 引擎文件路径不匹配

**症状：** 行动指南生成失败，日志 `python3: can't open file '/home/.../app/lib/engine/action-guide.py'`

**原因：** Mac 项目结构是 `app/app/lib/engine/`（Next.js app 在子目录），服务器上是 `app/` 即根目录 + `lib/engine/`。编译产物的路径是 `"app/lib/engine/action-guide.py"`，服务器上找不到。

**修复：**
```bash
mkdir -p /home/ubuntu/deeptalkAPP/app/lib
ln -s /home/ubuntu/deeptalkAPP/lib/engine /home/ubuntu/deeptalkAPP/app/lib/engine
```

**根本修复：** 源码中引擎路径统一用相对于项目根的路径（`lib/engine/action-guide.py`），不在路径上加 `app/` 前缀。

## 2. 数据库重建后孤儿 session

**症状：** 播种后打开访谈页面直接显示"生成行动指南"，不显示问题。

**原因：** 旧 session 仍在 `interview_sessions` 表中，但 `progress` 表已被清空。`getOrCreateSession` 找到旧 session 就返回，`getProgress` 返回 0 行，`nextPending` 找不到 "pending" 状态 → 返回 null → 前端认为已完成。

**修复：**
```sql
DELETE FROM interview_sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM progress);
```

## 3. 追问显示错误输入组件

**症状：** LLM 追问"你依赖直觉，最近一次凭直觉做的重要决定是什么？"但页面显示上一题的选择按钮。

**原因：** `submit()` 的 `probe` 分支只加了消息、设了 phase，没有更新 `current`。`current` 保持上一题的 `answerType: "choice"`，输入区渲染成选择题组件。

**修复：** 在 probe 分支创建合成题对象：
```typescript
setCurrent({
  id: q.id,
  dimension: q.dimension,
  topic: q.topic,
  seq: q.seq,
  text: result.text,    // 追问文本
  answerType: "free",   // 强制自由输入
  choices: [],
});
```

cross_probe 同此修复。

## 4. 多选 choice 题

**症状：** D2-A3 "你信任一个人的3个标准是什么？"只能选 1 个。

**原因：** choice 组件是单选，无多选支持。

**修复：**
- 检测函数：`/(\d+)个/.test(questionText)` 返回 N
- 前端渲染复选框，至多选 N 项
- `buildAnswer()` 用「、」拼接选中项
- `canSubmit` 判断 `selectedChoices.length > 0 && selectedChoices.length <= N`

## 5. LLM 调用超时

**症状：** 前端卡在"访谈员正在思考…"不恢复。

**排查顺序：**
1. `ssh ubuntu@81.68.254.248 "ls /home/ubuntu/deeptalkAPP/.env.local"` — 文件是否存在
2. `grep DEEPSEEK_API_KEY /home/ubuntu/deeptalkAPP/.env.local` — key 是否有值
3. `curl -X POST http://127.0.0.1:3000/api/interview/answer -H 'x-session-id: test-001' -d '{"question_id":"D1-A1","raw_answer":"test"}'` — API 是否响应
4. `pm2 logs deeptalk --lines 20 --nostream` — 看服务端日志
