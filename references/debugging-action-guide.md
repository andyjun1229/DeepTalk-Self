# 行动指南调试手册

## 症状

用户点击「生成行动指南」按钮后无反应（无错误提示、无 loading 状态、无网络请求）。

## 诊断步骤（按顺序）

### 1. 检查服务是否存活
```bash
ssh ubuntu@81.68.254.248 "pm2 list | grep deeptalk"
# 确认 status=online
curl -s -o /dev/null -w '%{http_code}' http://81.68.254.248:3000/interview
# 应返回 200
```

### 2. 看 PM2 错误日志
```bash
ssh ubuntu@81.68.254.248 "tail -80 ~/.pm2/logs/deeptalk-error.log"
```
前端无 JS 报错时，问题几乎一定在服务端 API 路由。常见错误：
- `python3: can't open file '.../action-guide.py': [Errno 2] No such file or directory`
- `table answers has no column named xxx`
- LLM API 调用超时

### 3. 检查引擎文件路径
```bash
# 编译产物引用的路径
ssh ubuntu@81.68.254.248 "grep -o 'action-guide.py[^\"]*' /home/ubuntu/deeptalkAPP/.next/server/app/api/action-guide/generate/route.js"
# 实际文件位置
ssh ubuntu@81.68.254.248 "ls -la /home/ubuntu/deeptalkAPP/lib/engine/action-guide.py"
```

**根因：** Mac 项目结构是 `app/app/lib/engine/`（嵌套），服务器上 `app/` 即 Next.js 根目录 + `lib/engine/`。编译时路径 `app/lib/engine/` 被写入 .next 产物，部署后不匹配。

**修复：**
```bash
ssh ubuntu@81.68.254.248 "mkdir -p /home/ubuntu/deeptalkAPP/app/lib && ln -s /home/ubuntu/deeptalkAPP/lib/engine /home/ubuntu/deeptalkAPP/app/lib/engine"
```

### 4. 检查数据库是否为空
```bash
ssh ubuntu@81.68.254.248 "cd /home/ubuntu/deeptalkAPP && python3 -c \"
import sqlite3; db = sqlite3.connect('data/interview.db')
print('questions:', db.execute('SELECT COUNT(*) FROM questions').fetchone()[0])
print('answers:', db.execute('SELECT COUNT(*) FROM answers').fetchone()[0])
print('progress:', db.execute('SELECT COUNT(*) FROM progress').fetchone()[0])
\""
```
如果 questions=0 → 数据库未播种，运行 `npm run seed`。

⚠️ **`npm run seed` 会清空旧数据**，先备份：`cp data/interview.db data/interview.db.bak`

**播种后还要清理孤儿 session：** 旧 session 在 DB 重建后仍有记录，但 progress 表为空。前端 `/api/interview/state` 的 `nextPending` 找不到 pending 题 → 返回 null → 直接跳到完成页。

修复：
```bash
ssh ubuntu@81.68.254.248 "cd /home/ubuntu/deeptalkAPP && python3 -c \"
import sqlite3; db = sqlite3.connect('data/interview.db')
db.execute('DELETE FROM interview_sessions WHERE id NOT IN (SELECT DISTINCT session_id FROM progress)')
db.commit()
print('Cleaned orphans')
\""
```

### 5. 直接测 Python 引擎
```bash
ssh ubuntu@81.68.254.248 "echo '用户经常逃避决策...' > /tmp/test-profile.txt && python3 /home/ubuntu/deeptalkAPP/lib/engine/action-guide.py /tmp/test-profile.txt"
```
应返回 JSON，含 `cards` 数组。

### 6. 直接测 API 端点
```bash
curl -s -X POST http://81.68.254.248:3000/api/action-guide \
  -H 'Content-Type: application/json' \
  -d '{"profile":"用户经常逃避决策，依赖他人意见。"}' | python3 -m json.tool
```

## 相关文件

| 文件 | 位置 |
|------|------|
| 引擎 | `lib/engine/action-guide.py` |
| API 路由 (POST) | `app/api/action-guide/route.ts` |
| 生成路由 (从 session) | `app/api/action-guide/generate/route.ts` |
| 编译产物 | `.next/server/app/api/action-guide/generate/route.js` |
| 数据库 | `data/interview.db` |
| 错误日志 | `~/.pm2/logs/deeptalk-error.log` |
