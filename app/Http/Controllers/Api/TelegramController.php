<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Goods; // 确保这里和你找到的模型名一致
use Illuminate\Http\Request;
use App\Service\OrderService;
use App\Service\OrderProcessService;
use App\Models\Pay;
use Illuminate\Support\Facades\DB;
use App\Exceptions\RuleValidationException;

class TelegramController extends Controller
{
    /**
     * =============================
     * 统一 Token 定义
     * =============================
     */
    private const API_TOKEN = 'xxxxmjj';


    /**
     * 获取商品列表
     */
    public function goodsList(Request $request)
    {
        // Token 校验
        if ($request->get("token") != self::API_TOKEN) {
            return response()->json(["msg" => "Unauthorized"], 401);
        }

        $goods = \App\Models\Goods::where("is_open", 1)
            ->withCount([
                "carmis" => function ($query) {
                    $query->where("status", 1); // 这里的 status 为 1 通常代表未售出
                },
            ])
            ->with("group")
            ->get();

        $data = $goods->map(function ($item) {
            // return $item->toArray(); //用这个可以返回所有字段
            return [
                "id" => $item->id,
                "name" => $item->gd_name,
                "price" => $item->actual_price, // 使用我们刚找到的 actual_price
                "stock" =>
                    $item->type == 1 ? $item->carmis_count : $item->in_stock,
                "description" => $item->description,
                "category" => $item->group ? $item->group->gp_name : "无分类",
                "cid" => $item->group_id,
            ];
        });

        return response()->json($data);
    }


    public function createOrder(Request $request)
    {
        $token = $request->input("token");

        // Token 校验
        if ($token !== self::API_TOKEN) {
            return response()->json(["msg" => "Unauthorized"], 401);
        }

        // 1. 初始化系统服务
        $orderService = app("Service\OrderService");
        $orderProcessService = app("Service\OrderProcessService");

        DB::beginTransaction();
        try {

            // 2. 模拟网页请求的数据结构
            // 假设你从 Bot 传来了 gid, payway, email, tg_id
            $gid = $request->input("gid");

            $goods = Goods::find($gid);
            if (!$goods) {
                throw new RuleValidationException("商品不存在");
            }

            // 3. 调用系统校验 (这会同步库存、校验商品状态)
            $orderService->validatorLoopCarmis($request); // 校验循环卡密
            $orderProcessService->setGoods($goods);

            // 数量默认 1
            $orderProcessService->setBuyAmount(1);

            // 支付方式
            $payId = $request->input("payway");
            $orderProcessService->setPayID($payId);

            // 必填基本信息
            $orderProcessService->setEmail($request->input("email"));
            $orderProcessService->setBuyIP($request->ip());

            // 特殊：记录 TG ID (如果有字段的话，没有就不设)
            // $orderProcessService->setOtherIpt(['tg_id' => $request->input('tg_id')]);

            // 4. 【关键】调用系统创建订单函数
            // 这一步会处理库存扣减、设置 created_at，并进入系统的过期监控逻辑
            $order = $orderProcessService->createOrder();

            DB::commit();

            $orderSn = $order->order_sn;

            // 5. 获取支付链接 (仿照系统逻辑)
            $pay = Pay::find($payId);
            if (!$pay) {
                return response()->json(["msg" => "支付方式不存在"], 400);
            }

            // 6. 构造 direct_url
            // 逻辑：/pay-gateway + 转义后的 handleroute + pay_check + order_sn

            // 第一次编码：/pay/yipay -> %2Fpay%2Fyipay
            // 第二次编码：%2Fpay%2Fyipay -> %252Fpay%252Fyipay
            $encodedRoute = urlencode(urlencode($pay->pay_handleroute));

            // 拼接成你要求的格式
            // 格式：https://fk.xxx.xyz/pay-gateway/%252Fpay%252Fyipay/alipay2/订单号
            $directUrl = url(
                "/pay-gateway/{$encodedRoute}/{$pay->pay_check}/{$orderSn}"
            );

            return response()->json([
                "msg" => "Success",
                "order_sn" => $orderSn,
                "pay_url" => url("/bill/{$orderSn}"), //这个是你提交订单后的网页地址
                "direct_url" => $directUrl, //这个是直接跳转到支付网关的地址
            ]);

        } catch (\Exception $e) {

            DB::rollBack();

            return response()->json([
                "msg" => $e->getMessage()
            ], 500);
        }
    }


    /**
     * 获取已开启的支付方式列表
     */
    public function payways(Request $request)
    {
        // 验证 token
        if ($request->get("token") != self::API_TOKEN) {
            return response()->json(["msg" => "Unauthorized"], 401);
        }

        $payways = \App\Models\Pay::query()
            ->where("is_open", 1)
            ->select("id", "pay_name", "pay_check", "pay_handleroute")
            ->orderBy("id", "asc")
            ->get();

        return response()->json([
            "msg" => "Success",
            "data" => $payways,
        ]);
    }


    /**
     * 查询订单状态
     */
    public function orderStatus(Request $request)
    {
        $orderSn = $request->get("order_sn");
        $token = $request->get("token");

        // 简单验证
        if ($token != self::API_TOKEN) {
            return response()->json(["msg" => "Unauthorized"], 401);
        }

        if (!$orderSn) {
            return response()->json(["msg" => "订单号不能为空"], 400);
        }

        // 查询订单
        $order = \App\Models\Order::where("order_sn", $orderSn)->first();

        if (!$order) {
            return response()->json(["msg" => "订单不存在"], 404);
        }

        // 获取状态映射表
        $statusMap = \App\Models\Order::getStatusMap();

        return response()->json([
            "msg" => "Success",
            "data" => [
                "order_sn" => $order->order_sn,
                "status" => $order->status, // 状态码数字
                "status_text" => $statusMap[$order->status] ?? "未知状态", // 状态名称
                "is_paid" =>
                    $order->status >= \App\Models\Order::STATUS_PENDING, // 是否已支付
            ],
        ]);
    }
}
