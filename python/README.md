# Python ツール

PC から CAN 経由でファームウェアを操作するサンプルです。**Linux（SocketCAN）専用** です。
メッセージ仕様は [../docs/can-protocol.md](../docs/can-protocol.md) を参照してください。

## 準備

```sh
pip install python-can
sudo ip link set can0 up type can bitrate 500000
```

USB-CAN アダプタなど、SocketCAN で `can0` として見えるインターフェースが必要です。

## send_once_args.py — 目標角度を1回送る

```sh
python3 send_once_args.py <角度1> <角度2> --id 0x6a [--iface can0]
```

| 引数 | 説明 |
|---|---|
| `角度1`, `角度2` | 目標角度（整数, 0〜360） |
| `--id` | 送信先 CAN ID。**`0x6a` を指定してください**（デフォルトの `0x69` はマイコンの送信 ID なので受け付けられません） |
| `--iface` | SocketCAN インターフェース（デフォルト `can0`） |

送信データは `01 <角度1上位> <角度1下位> <角度2上位> <角度2下位> FF FF FF` です。

例:

```sh
$ python3 send_once_args.py 220 90 --id 0x6a
sent OK
iface=can0 id=0x06A
arg1=220 -> bytes [00 DC]
arg2=90 -> bytes [00 5A]
payload (hex): 01 00 dc 00 5a ff ff ff
```

## monitor_and_ping.py — 角度の定期問い合わせ + 受信モニタ

```sh
python3 monitor_and_ping.py <間隔[秒]> [--id 0x6a] [--iface can0]
```

- 指定した間隔で `09 00 00 00 00 FF FF FF`（現在角度の要求）を `--id`（デフォルト `0x6a`）に送ります。
- バス上の全フレームを candump 風に表示します。
- 何かキーを押すと終了します（TTY でないときは Ctrl+C）。

例:

```sh
$ python3 monitor_and_ping.py 4
Press any key to stop.
Monitoring can0. Receiving like candump; sending to ID 0x06A every 4.0s.
TX -> can0  06A   [8]  09 00 00 00 00 FF FF FF
(1760500000.123456) can0  069   [8]  00 00 DC 00 5A FF FF FF
```

返信（ID `0x069`）の byte1-2 が軸1、byte3-4 が軸2 の現在角度（上位, 下位）です。上の例では 220°, 90° です。
