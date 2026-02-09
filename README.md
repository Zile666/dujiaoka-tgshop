# 🚀 独角发卡 + Telegram Bot 下单方案（完整适配版）

> 让 Telegram 下单体验 **完全对齐网页下单逻辑**，而不是“挂名对接”。

---

## 📌 项目背景

一直想给 **独角发卡** 对接一个 Telegram Bot，实现：

- TG 下单  
- 网页原生逻辑创建订单  
- 自动库存 / 卡密 / 过期 / 支付  
- 支付成功 **直接在 TG 推送卡密给用户**

搜索了一圈发现现有方案基本都是：

- ❌ 数据库直插（绕过核心逻辑）
- ❌ 两个项目表面联动，实际完全分离
- ❌ 支付、库存、卡密行为不一致

最终决定：

👉 **严格复用独角发卡原生下单流程，只是换一个入口（Telegram）**

在 AI 多轮调试辅助下，最终完成。

---

## 🎯 方案核心思路

**一句话总结：**

> Telegram 只是「前端」，下单仍然走独角发卡原生服务。

### 核心原则

- ✅ 不改数据库结构
- ✅ 不复制下单逻辑
- ✅ 不破坏原有支付方式
- ✅ TG / 网页订单完全一致

---

## 🧩 整体架构

Telegram Bot (python)
↓
独角发卡 API（新增 TG 专用接口）
↓
OrderProcessService（原生服务）
↓
支付 → 订单完成 → Telegram 推送卡密


---

## 🛠️ 需要改动的内容

只需要 **3 个 PHP 文件 + 1 个 Python Bot**

### ✅ 改动 / 新增文件

routes/api.php
app/Http/Controllers/Api/TelegramController.php
app/Jobs/TelegramPush.php
tgshop.py（Python）


---

## 1️⃣ 新增 API 路由

📍 文件位置：`routes/api.php`

用途：

给 Telegram Bot 提供 **数据获取 / 下单 / 查询状态** 的 API 接口。

```
Route::get('/tg/goods', [\App\Http\Controllers\Api\TelegramController::class, 'goodsList']);

// 创建订单（POST）
Route::post('/tg/create-order', [\App\Http\Controllers\Api\TelegramController::class, 'createOrder']);

Route::get('/tg/payways', [\App\Http\Controllers\Api\TelegramController::class, 'payways']);
Route::get('/tg/order-status', [\App\Http\Controllers\Api\TelegramController::class, 'orderStatus']);
```

## 2️⃣ Telegram API 控制器

📍 文件位置：

app/Http/Controllers/Api/TelegramController.php

（需新建）

### 关键点说明

- ❗ 严禁直接插表
- ❗ 必须调用 `OrderProcessService`
- 确保以下行为全部生效：

自动扣库存
卡密预占
自动过期
支付状态同步


📌 支付方式仍然沿用网页逻辑  

👉 TG 下单后 **跳转网页支付**

---

## 3️⃣ Telegram 支付成功推送卡密

📍 文件位置：

app/Jobs/TelegramPush.php

### 思路说明

独角发卡原生 Telegram 通知：

👉 只通知管理员  

这里复用 Job，在订单完成时：

- 判断是否是 TG 用户下单  
- 如果是 → 推送卡密给用户  

---

### 🧠 如何区分 TG 用户？

在 TG 下单时，把 `chat_id` 写进邮箱字段：

tg_{chat_id}@bot.com

例如：tg_123456789@bot.com

---

### 💡 核心新增代码

```php
// 正则匹配 tg_数字@bot.com
$botToken = dujiaoka_config_get('telegram_bot_token');

if (preg_match('/tg_(\d+)@bot\.com/', $this->order->email, $matches)) {
    $userChatId = $matches[1];

    $cardContent = $this->order->info;

    $userText = "🎉 *支付成功！您的卡密已送达*%0A%0A"
        . "📦 *商品名称*: " . $this->order->title . "%0A"
        . "💰 *实付金额*: " . $this->order->actual_price . "元%0A"
        . "🎫 *您的卡密信息*: %0A"
        . "--------------------------%0A"
        . $cardContent . "%0A"
        . "--------------------------%0A"
        . "🔖 *订单编号*: `" . $this->order->order_sn . "`%0A"
        . "📅 *购买时间*: " . $this->order->created_at;

    $userUrl = "https://api.telegram.org/bot{$botToken}/sendMessage?chat_id={$userChatId}&parse_mode=Markdown&text={$userText}";

    try {
        $client->post($userUrl);
    } catch (\Exception $e) {
        \Log::error("TG推送给用户失败: " . $e->getMessage());
    }
}
```
⚠️ 注意事项
如果开启了邮件通知，需要过滤这种邮箱格式

或改为这种不存在的邮箱：tg_数字@bot.mydomain

## 🤖 Telegram Bot（Python）

### 安装依赖

```bash
pip install python-telegram-bot requests
```

---

### 配置项（tgshop.py）

```python
TOKEN = '859xxx81:AAHqkxxxxqFA'
SHOP_URL = 'https://fk.xxx.xyz'
API_TOKEN_SECRET = 'xxxxmjj'
EXPIRE_TIME = 10  # 订单检测时间（分钟）
```

---

### 启动 Bot

```bash
python tgshop.py
```

---

## 🔗 支持深度链接

### 直达分类

```text
https://t.me/tgshiyong_bot?start=cid_1
```

### 直达商品

```text
https://t.me/tgshiyong_bot?start=pid_3
```

---

## ✅ 最终效果

- TG 下单 ≈ 网页下单  
- 统一库存 / 支付 / 卡密逻辑  
- 支付成功 TG 自动推送卡密  
- 无额外数据库、无魔改核心代码  

---

## 📎 适用人群

- 已使用 独角发卡  
- 想做 Telegram 自动发卡  
- 不想维护两套系统  
- 在意稳定性和安全性  

