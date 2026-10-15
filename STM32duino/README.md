# ファームウェア（STM32duino）

STM32F103C8T6（Bluepill）上で Arduino フレームワークを使って動くファームウェアです。

- SPI 接続の 14bit アブソリュート磁気エンコーダ ×2 で角度を読む
- CAN（eXoCAN, 500kbps）で目標角度を受け取る
- 2 個の DC モータを ON/OFF で目標角度へ動かす

CAN メッセージの仕様は [../docs/can-protocol.md](../docs/can-protocol.md) を参照してください。

## ビルド・書き込み

[PlatformIO](https://platformio.org/) を使います（[platformio.ini](platformio.ini)）。

| 項目 | 値 |
|---|---|
| platform / board | `ststm32` / `bluepill_f103c8` |
| framework | `arduino` |
| 依存ライブラリ | `exothink/eXoCAN @ ^1.0.3` |
| 書き込み | ST-Link（`upload_protocol = stlink`） |

```sh
pio run              # ビルド
pio run -t upload    # 書き込み
pio device monitor -b 115200   # デバッグ出力（Serial2 を USB-UART で接続した場合）
```

## ピン割り当て

| 機能 | ピン | 備考 |
|---|---|---|
| オンボード LED | PC13 | 現在は未使用 |
| エンコーダ1 CS | PB0 | |
| エンコーダ2 CS | PB1 | |
| SPI1 | PA5 (SCK) / PA6 (MISO) / PA7 (MOSI) | Arduino 標準 SPI |
| モータ1 方向 / 駆動 | PA15 / PB3 | コード上は `M1_D` / `M1_P` |
| モータ2 方向 / 駆動 | PB4 / PB5 | コード上は `M2_D` / `M2_P` |
| CAN RX / TX | PA11 / PA12 | `PORTA_11_12_XCVR`（外付けトランシーバ使用） |
| デバッグ UART（Serial2） | PA2 (TX) / PA3 (RX) | 115200bps |

> PA15・PB3・PB4 はデフォルトで JTAG に割り当てられているピンです。Arduino Core が SWD のみ有効にするので
> GPIO として使えていますが、デバッガ接続の設定を変えるときは注意してください。

> **軸とモータ端子の対応に注意**: エンコーダ1 の角度は M2 端子、エンコーダ2 の角度は M1 端子を駆動します
> （[known-issues.md #3](../docs/known-issues.md#3-軸番号とモータ端子が交差している)）。

## エンコーダ読み出し

- SPI: 100kHz, MSB First, **MODE1**
- 読み出しコマンド `0xFFFF` を 16bit 転送で送り、次の転送で前回コマンドの応答を受け取る（`delay(10)` を挟む）
- 上位 2bit（パリティ / エラーフラグ）を捨てて 14bit 値（0〜16383）にする
- AS5048A 互換のプロトコルです（ライブラリ版の呼び出しはコメントアウトして残っています）

## 角度計算

1. 2 軸の生値をそれぞれ **30 サンプルのリングバッファ** に入れて算術平均する
2. `deg = 平均値 / 16384 × 360` で度に変換する
3. 整数に切り捨てて現在角度 `pos_1`, `pos_2`（0〜359）とする

## モータ制御

目標角度 `tgt` と現在角度 `pos` の差を見て、毎ループ次のように出力します。

| 条件 | 出力 |
|---|---|
| `|pos − tgt| < 5` | 停止（方向=LOW, 駆動=LOW） |
| `pos > tgt` | 駆動=HIGH、方向は「up」側 |
| `pos < tgt` | 駆動=HIGH、方向は「down」側 |

方向ピンの論理は軸ごとに逆です（軸1: up=HIGH、軸2: up=LOW）。速度制御（PWM）はしていません。

## 処理の流れ

### `setup()`

1. CAN 初期化（500kbps、全メッセージ通過フィルタ、受信割り込み `canISR` を登録）
2. GPIO 初期化（CS=HIGH、モータ出力=LOW）
3. Serial2（115200bps）と SPI を開始
4. エンコーダを **100 回** 読んで移動平均バッファを埋める
5. 目標角度を現在角度にする（起動直後はモータが動かない）

### `loop()`

1. `cmd=9` で送信要求フラグが立っていれば、現在角度を ID `0x069` で送信
2. エンコーダ 2 軸を読み、移動平均で角度を更新
3. Serial2 に `pos_1 / tgt_1 <TAB> pos_2 / tgt_2` を出力
4. 受信済みの CAN フレームを処理（`canRead`）
5. モータ制御（`motor_work`）

CAN の受信自体は割り込み（`canISR`）でバッファに入り、ループ内の `canRead()` で解釈されます。

## 主な関数（[src/main.cpp](src/main.cpp)）

| 関数 | 役割 |
|---|---|
| `readRegister(cs)` | エンコーダ（0=CS1, 1=CS2）から 14bit 生値を読む |
| `move_ave()` | 移動平均と角度変換。`pos_1`, `pos_2` を更新 |
| `canISR()` | CAN 受信割り込み。フレームをバッファに格納 |
| `canRead(print)` | 受信フレームを解釈して目標角度の更新・送信要求を処理 |
| `motor_cmd(ch, dir, pwr)` | モータ端子の出力（`ch=1`→M1 端子、`ch=0`→M2 端子） |
| `motor_work()` | 目標と現在角度を比べてモータを駆動・停止 |
| `set_candata()` | 返信用の 8 バイトを組み立てる |

## 調整用パラメータ

| 定数 | 値 | 意味 |
|---|---|---|
| `AVE_NUM` | 30 | 移動平均のサンプル数 |
| `MOTOR_DZ` | 5 | 不感帯 [deg]（※軸2 は直書きの `5`） |
| `txMsgID` / `rxMsgID` | 0x069 / 0x06A | CAN 送信 / 受信 ID |

既知の問題は [../docs/known-issues.md](../docs/known-issues.md) にまとめています。
