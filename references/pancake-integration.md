# Waffo Pancake 支付集成要点

深谈项目接入 Waffo Pancake（国际商户记录商）的实践经验。

## 关键踩坑

### 1. webhook 必须用 raw text
```typescript
// ✅ 正确
const body = await req.text();
const event = verifyWebhook(body, sig);

// ❌ 错误 — 签名验证失败
const body = await req.json();
```

### 2. verifyWebhook 泛型默认值
```typescript
// 默认 T = Record<string, unknown>，.data 上无类型提示
// 需要显式传入自定义接口
interface MyData { orderId: string; orderMetadata?: Record<string, string> }
const event = verifyWebhook<MyData>(body, sig);
```

### 3. 支付会话无 productType
SDK 的 `CreateCheckoutSessionParams` 没有 `productType` 字段。产品类型由产品本身决定（一次性 vs 订阅），不需要在创建会话时指定。

### 4. metadata 通过 orderMetadata 回传
结账时传入的 `metadata: { sessionId }` 在 webhook 事件中通过 `event.data.orderMetadata?.sessionId` 获取，不是 `.data.metadata`。

### 5. 弹窗拦截问题
```typescript
// ❌ 被拦截：fetch 完成后 window.open 不是用户触发
const result = await fetch(...);
window.open(result.checkoutUrl, ...);

// ✅ 正确：先开同步窗口，再异步设置 URL
const w = window.open("", "_blank", "noopener,noreferrer");
const result = await fetch(...);
w.location.href = result.checkoutUrl;
```

### 6. ngrok 用于本地调试 webhook
- `brew install ngrok` → `ngrok http 3000`
- 不要用 localtunnel（会剥离 `X-Waffo-Signature` 头）
- 免费层每次重启 URL 变化，需重新配置

## 环境变量

```
WAFFO_MERCHANT_ID=MER_xxx
WAFFO_PRIVATE_KEY=<PEM 格式 RSA 私钥>
WAFFO_STORE_ID=STO_xxx
WAFFO_PRODUCT_ID=PROD_xxx
```

## 项目文件

| 文件 | 用途 |
|------|------|
| `lib/pancake.ts` | 客户端单例 |
| `app/api/checkout/route.ts` | 创建支付会话 |
| `app/api/webhooks/pancake/route.ts` | 接收回调，调 `grantFullAccess()` |
| `lib/db/index.ts` | `grantFullAccess()` 幂等写入权益 |

## 测试卡

| 类型 | 卡号 |
|------|------|
| Visa 成功 | `4576 7500 0000 0110` |
| Visa 拒付 | `4576 7500 0000 0220` |
| 有效期 | 任意未来日期 |
| CVC | 任意 3 位 |
