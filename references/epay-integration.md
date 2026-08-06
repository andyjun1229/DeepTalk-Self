# 易支付（Epay）集成参考

标准中国个人支付网关协议，适用于 `epay.jylt.cc` 及同类平台。

## 核心流程

```
商户创建订单 → 拼接参数 + MD5签名 → GET跳转支付页 →
用户扫码支付 → 平台异步通知(notify) → 平台同步跳转(return) →
商户验签 + 业务处理 → 返回 "success"
```

## 参数规范

### 下单参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `pid` | 是 | 商户 ID |
| `type` | 是 | `alipay` / `wxpay` |
| `out_trade_no` | 是 | 商户订单号（唯一） |
| `notify_url` | 是 | 异步通知地址 |
| `return_url` | 是 | 同步跳转地址 |
| `name` | 是 | 商品名称 |
| `money` | 是 | 金额（如 "9.90"） |
| `sign` | 是 | MD5 签名 |
| `sign_type` | 是 | 固定 `MD5` |

### 回调参数（notify / return）

| 参数 | 说明 |
|------|------|
| `pid` | 商户 ID |
| `trade_no` | 平台订单号 |
| `out_trade_no` | 商户订单号 |
| `type` | 支付方式 |
| `name` | 商品名称 |
| `money` | 金额 |
| `trade_status` | `TRADE_SUCCESS` 表示支付成功 |
| `sign` | MD5 签名 |
| `sign_type` | `MD5` |

## MD5 签名算法

```
1. 取所有参数（排除 sign 和 sign_type，排除空值）
2. 按 key 字母序排列
3. 拼接为 k1=v1&k2=v2&...&kn=vn 格式
4. 末尾追加商户 KEY
5. MD5 取 32 位小写十六进制
```

TypeScript 实现：
```typescript
function sign(params: Record<string, string>, key: string): string {
  const sorted = Object.keys(params)
    .filter(k => k !== "sign" && k !== "sign_type" && params[k] !== "")
    .sort();
  const raw = sorted.map(k => `${k}=${params[k]}`).join("&") + key;
  return crypto.createHash("md5").update(raw).digest("hex");
}
```

### notify_url 传自定义参数

通过 `?sid=${sessionId}` 附加在 notify_url 末尾。回调时先从 URL 提取 sid，再对剩余参数验签。

```typescript
// 下单时
notifyUrl: `https://example.com/api/webhooks/epay?sid=${encodeURIComponent(sessionId)}`

// 回调时
const { sid, ...params } = raw;  // 分离自定义参数
if (!verifyNotify(params)) return fail;  // 用纯净参数验签
if (params.trade_status !== "TRADE_SUCCESS") return ok;
// 金额校验
if (params.money !== expectedAmount) return fail;
```

## 回调处理注意事项

- 异步通知可能重复发送，必须幂等
- 返回 `"success"` 纯文本（非 JSON），否则平台重试
- 金额必须校验，防止篡改
- 不支持 JSON body，参数在 URL query 或 `application/x-www-form-urlencoded` 中
- 建议先返回 success 再异步处理业务逻辑

## 深谈项目配置

| 项 | 值 |
|-----|-----|
| 平台 | epay.jylt.cc |
| API 端点 | `/submit.php` |
| PID | 1785811403 |
| 环境变量 | `EPAY_PID`, `EPAY_KEY`, `EPAY_API_URL` |
| 代码 | `lib/epay.ts`（sign + createOrder） |
| API 路由 | `/api/checkout/epay`（下单）, `/api/webhooks/epay`（回调） |
