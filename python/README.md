# Python ツール

PC から CAN 経由でファームウェアを操作するサンプルです。Linux（SocketCAN）と macOS（USB-CAN アダプタ直結）で動きます。
メッセージ仕様は [../docs/can-protocol.md](../docs/can-protocol.md) を参照してください。

| ファイル | 内容 |
|---|---|
| [send_once_args.py](send_once_args.py) | 目標角度を1回送る |
| [monitor_and_ping.py](monitor_and_ping.py) | 現在角度を定期的に問い合わせ、受信を表示する |
| [jog.py](jog.py) | キー操作で2軸を動かし、角度を記録して可動範囲を求める |
| [can_bus.py](can_bus.py) | CAN バスを開く共通処理（インターフェースの切り替え） |

## 機構的な制限（可動範囲）

| 軸 | 可動範囲 |
|---|---|
| 軸1 | **180〜210°** |
| 軸2 | **100〜180°** |

目標角度を送るツールは、この範囲を守ります。値は [can_bus.py](can_bus.py) の `AXIS_LIMITS` で設定しています。

- `send_once_args.py`: 範囲外の角度を指定するとエラーになり、送信しません。
- `jog.py`: 目標は範囲の端で止まり、`LIMIT` と記録されます。開始時に範囲外にいる軸は、範囲に戻る向きの操作だけを受け付けます。

ファームウェア側には制限がないので、手作業でフレームを送るときは注意してください。

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
cd python
python3 -m venv .venv
source .venv/bin/activate          # 以降、このターミナルでは python3 が .venv のものになる
pip install -r requirements.txt
brew install libusb                # gs_usb を使う場合
```

新しいターミナルを開いたときは、`source .venv/bin/activate` をもう一度実行してください
（または `.venv/bin/python jog.py` のように直接指定します）。

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
| `角度1`, `角度2` | 目標角度（整数）。軸1 は 180〜210、軸2 は 100〜180 |
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

## jog.py — キー操作で動かして可動範囲を記録する

```sh
python3 jog.py [--step 5] [--stall 3.0] [--log ファイル名.csv] [--interface ...]
```

| キー | 動作 |
|---|---|
| `A` / `S` | 軸1 の目標を −step / +step（大文字・小文字どちらでも可） |
| `Z` / `X` | 軸2 の目標を −step / +step |
| スペース | 終了（その場で停止し、集計を表示） |

- `--step` は1回押したときに動かす角度です（初期値5°）。目標は上の可動範囲に制限します。
  ファームの不感帯が5°なので、現在角度と目標の差が5°未満になるとモータは止まります（1回押しても動かないことがあります）。
- それ以外のキー（矢印キー、日本語入力の文字など）は無視します。
- 0.2 秒ごとに現在角度を取得して表示し、CSV（`time_s, pos1, pos2, tgt1, tgt2, event`）に記録します。
  ファイル名を指定しない場合は `jog_YYYYmmdd_HHMMSS.csv` になります。
- 終了時に、実測した角度の **最小・最大・可動幅** を軸ごとに表示し、`<ログ名>_summary.txt` にも保存します。
- **停止判定**: 目標に届いていないのに `--stall` 秒間（初期値3秒）ほとんど動かない軸があると、機構の端に当たったとみなします。
  そのときは停止コマンド（cmd=0）を送り、目標を現在位置に戻します。可動範囲を調べるときは、このまま端まで押していけば止まります。
- 終了時や Ctrl+C のときも必ず停止コマンドを送ります。
- ファームは受信フレームを1つしか保持できないので、送信の間隔を 0.1 秒以上あけています。
  さらに取りこぼし対策として、目標角度は2回送ります。
- 端末（TTY）から実行してください。

画面表示の例（`[最小..最大]` が記録中の可動範囲）:

```
axis1 203 -> 206  [196..203]   axis2 162 -> 164  [162..164]
```

終了時の集計の例:

```
=== Range of motion ===
Duration: 20.3 s
axis1: min=196  max=207  range= 11 deg
axis2: min=162  max=176  range= 14 deg
final: axis1=198 axis2=163
```

## トラブルシューティング

- **返信がなく、アダプタからエラーフレーム（ID `0x024` など）が出る**: ACK エラーで、バス上に応答するノードがいません。
  マイコンの電源、CANH/CANL の配線、GND の共通化、終端抵抗（120Ω × 両端）を確認してください。
- **送信がタイムアウトする / 開けない（I/O Error）**: ACK のないフレームを再送し続けてアダプタが詰まっています。
  USB を抜き差ししてください。
