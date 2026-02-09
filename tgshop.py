import logging
import requests
import time
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

#pip install python-telegram-bot requests

# --- 配置区 ---
TOKEN = '8433xxxx15:AAxxxxxxxxnq9SdlcGObXYg_Nlake9qlY' 
SHOP_URL = 'https://shop.xxx.xx'
API_TOKEN_SECRET = 'xxxx'
EXPIRE_TIME = 12  #订单检测时间（分钟）

# 模拟浏览器 Header，防止被防火墙拦截
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 缓存配置
CACHE_TTL = 300  # 缓存有效期（秒），这里设为 5 分钟
cached_goods = None
last_fetch_time = 0
PAY_CACHE_TTL = 300  # 支付方式缓存时间：5分钟
cached_payways = None
last_pay_fetch_time = 0

# --------------

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

async def fetch_goods():
    global cached_goods, last_fetch_time
    current_time = time.time()

    # 如果缓存存在且未过期，直接返回缓存
    if cached_goods and (current_time - last_fetch_time < CACHE_TTL):
        print("DEBUG: 使用内存缓存数据")
        return cached_goods

    # 否则请求后端接口
    try:
        print("DEBUG: 缓存过期或不存在，从接口拉取新数据...")
        params = {"token": API_TOKEN_SECRET}
        res = requests.get(f"{SHOP_URL}/api/goods", params=params, headers=headers, timeout=10)
        # 打印一下实际收到的内容，方便你在控制台调试
#        print(f"API Response: {response.text}") 
        if res.status_code == 200:
            data = res.json()
            # 更新缓存
            cached_goods = data
            last_fetch_time = current_time
            return data
    except Exception as e:
        print(f"Fetch error: {e}")
        # 如果请求失败但有旧缓存，可以暂时返回旧缓存兜底
        if cached_goods:
            return cached_goods
    return []

async def fetch_payways():
    """
    从后端接口动态获取已开启的支付方式，带内存缓存。
    """
    global cached_payways, last_pay_fetch_time
    current_time = time.time()

    # 1. 检查缓存是否有效
    if cached_payways and (current_time - last_pay_fetch_time < PAY_CACHE_TTL):
        print("DEBUG: 使用支付方式内存缓存")
        return cached_payways

    # 2. 缓存失效，请求后端接口
    try:
        print("DEBUG: 正在从后端拉取支付方式列表...")
        # 这里的 SHOP_URL 和 API_TOKEN_SECRET 请确保在脚本顶部已定义
        params = {"token": API_TOKEN_SECRET}
        # 如果您之前改成了 POST，请根据实际情况调整为 requests.post
        res = requests.get(f"{SHOP_URL}/api/payways", params=params, headers=headers, timeout=10)
        
        if res.status_code == 200:
            data = res.json().get('data', [])
            # 更新缓存
            cached_payways = data
            last_pay_fetch_time = current_time
            return data
        else:
            print(f"API Error: {res.status_code} - {res.text}")
            
    except Exception as e:
        print(f"Fetch Payways Error: {e}")
        # 如果请求失败但有旧数据，返回旧数据兜底
        if cached_payways:
            return cached_payways
            
    return []

def clean_html(raw_html):
    import re, html
    if not raw_html: return ""
    # 强制去掉所有标签，只保留换行
    content = re.sub(r'<(br|p|div)[^>]*>', '\n', raw_html)
    clean_text = re.sub(r'<[^>]+>', '', content) # 这一行是关键
    return html.escape(html.unescape(clean_text)) # escape 是为了防止描述里的 & 符号再次报错

async def order_status_monitor(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    # 强制获取最新的 data 并确保它是可写的
    data = job.data
    chat_id = data['chat_id']
    message_id = data['message_id']
    order_sn = data['order_sn']
    
    # 1. 计数逻辑优化：手动计数并打印，方便调试
    data['retry_count'] = data.get('retry_count', 0) + 1
    current_count = data['retry_count']
    print(f"DEBUG: 订单 {order_sn} 第 {current_count} 次检查")

    try:
        params = {"token": API_TOKEN_SECRET, "order_sn": order_sn}
        res = requests.get(f"{SHOP_URL}/api/order-status", params=params, headers=headers, timeout=5)
        
        if res.status_code == 200:
            res_data = res.json().get('data', {})
            # 2. 强转 status 为整数，防止字符串比对失败
            status = int(res_data.get('status', 0))
            status_text = res_data.get('status_text', '未知')

            # --- 逻辑 A：支付成功 ---
            if status >= 2:
                print(f"DEBUG: 订单 {order_sn} 已支付，停止任务")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"🎉 <b>订单支付成功！</b>\n\n单号：<code>{order_sn}</code>\n状态：<b>{status_text}</b>\n\n✅ 卡密已私聊发送，请查收。",
                    reply_markup=None,
                    parse_mode="HTML"
                )
                job.schedule_removal()
                return

            # --- 逻辑 B：检测到系统过期 ---
            if status == -1:
                print(f"DEBUG: 订单 {order_sn} 系统判定已过期")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ <b>订单已失效</b>\n\n单号：<code>{order_sn}</code>\n原因：系统已判定该订单超时。",
                    reply_markup=None,
                    parse_mode="HTML"
                )
                job.schedule_removal()
                return

        # --- 逻辑 C：Bot 强制超时判断（放在请求逻辑外，确保请求失败也能停） ---
        if current_count >= EXPIRE_TIME:
            print(f"DEBUG: 订单 {order_sn} 到达 {EXPIRE_TIME} 分钟上限，强制停止")
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ <b>订单已过期</b>\n\n单号：<code>{order_sn}</code>\n原因：{EXPIRE_TIME} 分钟内未检测到支付信息。",
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except:
                pass # 消息可能已被用户删除
            job.schedule_removal()
            return

    except Exception as e:
        print(f"轮询错误: {e}")
        # 如果报错次数也太多，也停掉
        if current_count >= 10:
            job.schedule_removal()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令，支持深度链接解析"""
    args = context.args
    
    if args:
        payload = args[0]
        
        # 处理分类跳转: cid_数字
        if payload.startswith("cid_"):
            cid = payload.replace("cid_", "")
            if cid.isdigit(): # 确保是数字 ID
                return await category_button(update, context, direct_cid=cid)

        # 处理直接购买跳转: pid_数字
        elif payload.startswith("pid_"):
            pid = payload.replace("pid_", "")
            if pid.isdigit(): # 确保是数字 ID
                return await buy_button(update, context, direct_pid=pid)

    # 如果没有参数，或参数格式错误，显示主菜单
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """抽离出的主菜单显示逻辑"""
    goods_data = await fetch_goods()
    
    if not goods_data:
        text = "❌ 暂时无法获取商品数据，请检查后端接口。"
        markup = None
    else:
        # --- 修改部分开始 ---
        seen_cid = set()
        keyboard = []
        for g in goods_data:
            cid = g['cid']
            # 如果这个分类 ID 还没被添加过，就加到键盘里
            if cid not in seen_cid:
                keyboard.append([InlineKeyboardButton(f"📂 {g['category']}", callback_data=f"cat_{cid}")])
                seen_cid.add(cid)
        # --- 修改部分结束 ---
        markup = InlineKeyboardMarkup(keyboard)
        text = "🛒 欢迎使用JR发卡机器人\n请选择商品分类："

    if update.message:
        await update.message.reply_text(text, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)

async def category_button(update: Update, context: ContextTypes.DEFAULT_TYPE, direct_cid=None):
    query = update.callback_query
    
    # 1. 获取目标 CID (分类ID)
    if direct_cid:
        target_cid = str(direct_cid)
    else:
        await query.answer()
        # 按钮点击时，callback_data 格式为 "cat_1"
        target_cid = str(query.data.split('_')[1])
    
    # 2. 获取数据
    goods_data = await fetch_goods()
    
    # 3. 【核心修改】根据接口返回的 'cid' 字段过滤商品
    filtered_goods = [g for g in goods_data if str(g.get('cid')) == target_cid]
    
    if not filtered_goods:
        text = "❌ 该分类下暂无商品。"
        if query: await query.edit_message_text(text)
        else: await update.message.reply_text(text)
        return

    # 获取分类名称用于标题展示
    cat_name = filtered_goods[0].get('category', '分类')

    # 4. 缓存详情 (供 buy_button 使用)
    if 'goods_cache' not in context.user_data:
        context.user_data['goods_cache'] = {}
    for g in filtered_goods:
        context.user_data['goods_cache'][str(g['id'])] = g

    # 5. 构建键盘
    keyboard = [[InlineKeyboardButton(f"{g['name']} | 💰{g['price']}", callback_data=f"buy_{g['id']}")] for g in filtered_goods]
    keyboard.append([InlineKeyboardButton("⬅️ 返回分类", callback_data="back_to_cats")])
    
    text = f"📂 【{cat_name}】分类下的商品："
    markup = InlineKeyboardMarkup(keyboard)

    # 6. 响应用户
    if query:
        await query.edit_message_text(text=text, reply_markup=markup)
    else:
        await update.message.reply_text(text=text, reply_markup=markup)
        
# 修改后的 buy_button 函数
async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE, direct_pid=None):
    query = update.callback_query
    
    # 1. 判定入口
    if direct_pid:
        pid = str(direct_pid)
    else:
        await query.answer()
        pid = query.data.split('_')[1]
    
    context.user_data['selected_pid'] = pid
    
    # 2. 获取商品详情
    good_info = context.user_data.get('goods_cache', {}).get(str(pid))
    if not good_info:
        all_goods = await fetch_goods()
        good_info = next((g for g in all_goods if str(g.get('id')) == str(pid)), None)

    if not good_info:
        error_text = "❌ 未找到该商品或商品已下架。"
        if query: await query.edit_message_text(error_text)
        else: await update.message.reply_text(error_text)
        return

    # --- 新增：库存校验逻辑 ---
    stock = int(good_info.get('stock', 0))
    is_out_of_stock = stock <= 0
    # -----------------------

    # 3. 渲染文案
    raw_desc = good_info.get('description') or "暂无描述"
    safe_desc = clean_html(raw_desc)

    # 在文案里加上库存显示，方便用户看
    stock_text = f"<code>{stock}</code>" if not is_out_of_stock else "<b>❌ 已售罄</b>"
    
    detail_text = (
        f"<b>🏷️ 商品名称</b>：{good_info['name']}\n"
        f"<b>💰 商品价格</b>：<code>{good_info['price']} 元</code>\n"
#        f"<b>📦 剩余库存</b>：{stock_text}\n"
        f"<b>📝 商品详情</b>：\n"
        f"--------------------------\n"
        f"{safe_desc}\n"
        f"--------------------------\n"
    )

    if is_out_of_stock:
        detail_text += "<b>⚠️ 抱歉，该商品目前缺货，请选择其他商品。</b>"
    else:
        detail_text += "<b>请选择您的支付方式：</b>"

    try:
        keyboard = []
        
        # 4. 根据库存情况构建键盘
        if is_out_of_stock:
            # 如果缺货，不显示支付按钮，只显示一个置灰的提示按钮（或者干脆不显示）
            keyboard.append([InlineKeyboardButton("🚫 暂时无货", callback_data="none")])
        else:
            # 有货，正常获取支付方式
            payways = await fetch_payways()
            # ✅ 如果没有任何支付方式（接口关闭 / 出错 / 空数组）
            if not payways:
                keyboard.append([
                    InlineKeyboardButton("⚠️ 暂无可用支付方式", callback_data="none")
                ])
            else:
                pay_buttons = [
                    InlineKeyboardButton(f"💳 {way['pay_name']}",callback_data=f"pay_{way['id']}")
                    for way in payways
                ]

                # 每 2 个按钮一行
                for i in range(0, len(pay_buttons), 2):
                    keyboard.append(pay_buttons[i:i + 2])

        # 5. 返回按钮
        target_cid = good_info.get('cid')
        keyboard.append([InlineKeyboardButton("⬅️ 返回商品列表", callback_data=f"cat_{target_cid}")])
        markup = InlineKeyboardMarkup(keyboard)

        # 6. 输出
        if query:
            await query.edit_message_text(text=detail_text, reply_markup=markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text=detail_text, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        print(f"Error in buy_button: {e}")
        error_msg = f"⚠️ 内容解析失败，请检查格式。\n{detail_text[:100]}"
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ 返回分类", callback_data="back_to_cats")]])
        if query: await query.edit_message_text(text=error_msg, reply_markup=back_markup)
        else: await update.message.reply_text(text=error_msg, reply_markup=back_markup)

# 新增处理最终下单的函数
# 修改后的 final_order 函数
async def final_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("正在生成订单...")
    
    pay_id = query.data.split('_')[1]
    # 1. 这里的键名要和 buy_button 存入时一致
    pid = context.user_data.get('selected_pid') 
    chat_id = query.message.chat_id

    # 2. 这里的 payload 字段要和你的 PHP 接口接收的字段一致
    payload = {
        'gid': pid,        # PHP 接口里如果是用 $request->input('gid')，这里就叫 gid
        'payway': pay_id,
        'email': f"tg_{chat_id}@bot.com",
        'tg_id': chat_id,
        'token': API_TOKEN_SECRET
    }
    
    try:
        # 注意：这里的 URL 要和你 PHP 新写的接口路径一致
        res = requests.post(f"{SHOP_URL}/api/create-order", data=payload, timeout=10)
        result = res.json()
#        print(result)
        if res.status_code == 200:
            # 确保 PHP 返回了这些字段
            direct_url = result.get('direct_url')
            order_sn = result.get('order_sn') 
            
            keyboard = [[InlineKeyboardButton("🚀 立即支付", url=direct_url)]]
            
            # 3. 文案微调 (使用 HTML 保持风格统一，Markdown 有时会因为特殊字符报错)
            text = (
                f"✅ <b>订单创建成功！</b>\n\n"
                f"单号：<code>{order_sn}</code>\n"
                f"💰 请在 {EXPIRE_TIME} 分钟内完成支付。\n"
                f"✨ 支付完成后，卡密将通过 Bot 自动发送。"
            )

            message = await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            
            # 4. 启动状态监控任务
            context.job_queue.run_repeating(
                order_status_monitor, 
                interval=60,      # 每 60 秒检查一次
                first=60,         # 1 分钟后执行第一次
                data={
                    'chat_id': chat_id, 
                    'message_id': message.message_id,
                    'order_sn': order_sn,
                    'retry_count': 0  
                }
            )
            
        else:
            await query.edit_message_text(text=f"❌ 下单失败：{result.get('msg', '未知错误')}")
            
    except Exception as e:
        print(f"Final order error: {e}")
        await query.edit_message_text(text=f"❌ 连接服务器失败: {str(e)}")

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "开始")
    ])


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start, pattern="^back_to_cats$")) # 修复返回键
    app.add_handler(CallbackQueryHandler(category_button, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(buy_button, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(final_order, pattern="^pay_"))
    print("PTB Bot 运行中...")
    app.run_polling()

if __name__ == "__main__":
    main()