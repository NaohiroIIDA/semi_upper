# Python ツール

PC から CAN 経由でファームウェアを操作するサンプルです。Linux（SocketCAN）と macOS（USB-CAN アダプタ直結）で動きます。
メッセージ仕様は [../docs/can-protocol.md](../docs/can-protocol.md) を参照してください。

| ファイル | 内容 |
|---|---|
| [send_once_args.py](send_once_args.py) | 目標角度を1回送る |
| [monitor_and_ping.py](monitor_and_ping.py) | 現在角度を定期的に問い合わせ、受信を表示する |
| [can_bus.py](can_bus.py) | CAN バスを開く共通処理（インターフェースの切り替え） |

## 対応インターフェース

`--interface` で切り替えます。省略時は Linux なら `socketcan`、それ以外なら `gs_usb` です。

| `--interface` | 対象 | `--channel` | 動作確認 |
|---|---|---|---|
| `socketcan` | Linux の `can0` など | `can0`（省略時） | — |
| `gs_usb` | candleLight（gs_usb ファーム）を USB 直結 | デバイス番号 `0`（省略時） | macOS + candleLight で確認済み |
| `slcan` | CANable / CANable2（slcan ファーム） | `/dev/cu.usbmodemXXXX`（省略時は自動検出） | macOS で送信のみ確認 |

ビットレートは `--bitrate`（省略時 500000）です。`socketcan` では `ip link` 側で設定します。

## 準備

### Linux（SocketCAN）

```sh
pip install python-can
sudo ip link set can0 up type can bitrate 500000
```

### macOS

```sh
pip install python-can gs_usb pyusb pyserial
brew install libusb        # gs_usb を使う場合
```

- ドライバのインストールは不要です。
- Homebrew の libusb（`/opt/homebrew/lib` または `/usr/local/lib`）は `can_bus.py` が自動で読み込みます。
- macOS の gs_usb は、まれに `Access denied` などで開けないことがあるので、`can_bus.py` が3回までリトライします。
- 接続したアダプタが認識されているかは次のコマンドで確認できます。
  ```sh
  ioreg -p IOUSB -l -w0 | grep '"USB Product Name"'
  ```

## send_once_args.py — 目標角度を1回送る

```sh
python3 send_once_args.py <角度1> <角度2> [--id 0x6a] [--interface ...] [--channel ...]
```

| 引数 | 説明 |
|---|---|
| `角度1`, `角度2` | 目標角度（整数, 0〜360） |
| `--id` | 送信先 CAN ID（省略時 `0x6a`） |

送信データは `01 <角度1上位> <角度1下位> <角度2上位> <角度2下位> FF FF FF` です。**送るとモータが動く** ので注意してください。

`gs_usb` では、相手の ACK（アダプタからの送信完了エコー）を受け取ってから終了します。
1 秒以内に ACK がなければ `send failed: no ACK` と表示します。
（エコーを読まずに閉じると candleLight が詰まり、抜き差しが必要になるためです。）

例:

```sh
$ python3 send_once_args.py 193 164
sent OK
interface=gs_usb channel=0 id=0x06A
arg1=193 -> bytes [00 C1]
arg2=164 -> bytes [00 A4]
payload (hex): 01 00 c1 00 a4 ff ff ff
```

## monitor_and_ping.py — 角度の定期問い合わせ + 受信モニタ

```sh
python3 monitor_and_ping.py <間隔[秒]> [--id 0x6a] [--interface ...] [--channel ...]
```

- 指定した間隔で `09 00 00 00 00 FF FF FF`（現在角度の要求）を `--id`（省略時 `0x6a`）に送ります。
- バス上の受信フレームを candump 風に表示します（自分の送信のエコーは表示しません）。
- 何かキーを押すと終了します（TTY でないときは Ctrl+C）。

例（macOS + candleLight）:

```sh
$ python3 monitor_and_ping.py 1
Press any key to stop.
Monitoring gs_usb0. Receiving like candump; sending to ID 0x06A every 1.0s.
TX -> gs_usb0  06A   [8]  09 00 00 00 00 FF FF FF
(1792057427.926903) gs_usb0  069   [8]  00 00 C1 00 A5 FF FF FF
```

返信（ID `0x069`）の byte1-2 が軸1、byte3-4 が軸2 の現在角度（上位, 下位）です。上の例では 193°, 165° です。

## トラブルシューティング

- **返信がなく、アダプタからエラーフレーム（ID `0x024` など）が出る**: ACK エラーで、バス上に応答するノードがいません。
  マイコンの電源、CANH/CANL の配線、GND の共通化、終端抵抗（120Ω × 両端）を確認してください。
- **送信がタイムアウトする / 開けない（I/O Error）**: ACK のないフレームを再送し続けてアダプタが詰まっています。
  USB を抜き差ししてください。
