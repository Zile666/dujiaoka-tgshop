<?php

use Illuminate\Http\Request;

/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
|
| Here is where you can register API routes for your application. These
| routes are loaded by the RouteServiceProvider within a group which
| is assigned the "api" middleware group. Enjoy building your API!
|
*/

Route::middleware('auth:api')->get('/user', function (Request $request) {
    return $request->user();
});

Route::get('/goods', [\App\Http\Controllers\Api\TelegramController::class, 'goodsList']);
// 改为 post
Route::post('/create-order', [\App\Http\Controllers\Api\TelegramController::class, 'createOrder']);
Route::get('/payways', [\App\Http\Controllers\Api\TelegramController::class, 'payways']);
Route::get('/order-status', [\App\Http\Controllers\Api\TelegramController::class, 'orderStatus']);