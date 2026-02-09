<?php

namespace App\Jobs;

use App\Models\Order;
use GuzzleHttp\Client;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;


class TelegramPush implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * 任务最大尝试次数。
     *
     * @var int
     */
    public $tries = 2;

    /**
     * 任务运行的超时时间。
     *
     * @var int
     */
    public $timeout = 30;

    /**
     * @var Order
     */
    private $order;

    /**
     * 商品服务层.
     * @var \App\Service\PayService
     */
    private $goodsService;


    /**
     * Create a new job instance.
     *
     * @return void
     */
    public function __construct(Order $order)
    {
        $this->order = $order;
        $this->goodsService = app('Service\GoodsService');
    }

    /**
     * Execute the job.
     *
     * @return void
     */
    public function handle()
    {
        $goodInfo = $this->goodsService->detail($this->order->goods_id);
        $formatText = '*'. __('dujiaoka.prompt.new_order_push').'('.$this->order->actual_price.'元)*%0A'
        . __('order.fields.order_id') .': `'.$this->order->id.'`%0A'
        . __('order.fields.order_sn') .': `'.$this->order->order_sn.'`%0A'
        . __('order.fields.pay_id') .': `'.$this->order->pay->pay_name.'`%0A'
        . __('order.fields.title') .': '.$this->order->title.'%0A'
        . __('order.fields.actual_price') .': '.$this->order->actual_price.'%0A'
        . __('order.fields.email') .': `'.$this->order->email.'`%0A'
        . __('goods.fields.gd_name') .': `'.$goodInfo->gd_name.'`%0A'
        . __('goods.fields.in_stock') .': `'.$goodInfo->in_stock.'`%0A'
        . __('order.fields.order_created') .': '.$this->order->created_at;
        $client = new Client([
            'timeout' => 30,
            'proxy'=> ''
        ]);
		
		$botToken = dujiaoka_config_get('telegram_bot_token');
        // --- 2. 推送给管理员 (保持不变) ---
        $adminId = dujiaoka_config_get('telegram_userid');
        if ($adminId) {
            $apiUrl = "https://api.telegram.org/bot{$botToken}/sendMessage?chat_id={$adminId}&parse_mode=Markdown&text={$formatText}";
            $client->post($apiUrl);
        }
		
		// --- 3. 核心修改：检查是否是 TG 用户下单，并推送卡密 ---
		//修改后需要 php artisan queue:restart
        // 正则匹配 tg_数字@bot.com
        if (preg_match('/tg_(\d+)@bot\.com/', $this->order->email, $matches)) {
            $userChatId = $matches[1]; // 提取出 chat_id
            
            // 组装发给用户的卡密内容 (参考 OrderUpdated.php)
            // $this->order->info 就是独角发卡自动提取的卡密字段
            $cardContent = $this->order->info; 
            
            $userText = "🎉 *支付成功！您的卡密已送达*%0A%0A"
                . "📦 *商品名称*: " . $this->order->title . "%0A"
                . "💰 *实付金额*: " . $this->order->actual_price . "元%0A"
                . "🎫 *您的卡密信息*: %0A"
                . "--------------------------%0A"
                . $cardContent . "%0A%0A" 
                . "--------------------------%0A"
//                . "`%0A" . $cardContent . "%0A`%0A"   // 另一种格式，点击复制的
                . "🔖 *订单编号*: `" . $this->order->order_sn . "`%0A"
                . "📅 *购买时间*: " . $this->order->created_at . "%0A%0A"
                . "✨ 感谢您的使用，欢迎再次光临！";

            $userUrl = "https://api.telegram.org/bot{$botToken}/sendMessage?chat_id={$userChatId}&parse_mode=Markdown&text={$userText}";
            
            try {
                $client->post($userUrl);
            } catch (\Exception $e) {
                // 如果用户屏蔽了 Bot 或 ID 失效，避免 Job 报错死循环
                \Log::error("TG推送给用户失败: " . $e->getMessage());
            }
		}
    }
}
