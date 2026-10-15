# semi_upper

STM32F103C8T6（Bluepill）で **2軸の DC モータを角度制御** するファームウェアと、
PC（Linux / SocketCAN）から **CAN 経由で目標角度を送る・現在角度を取得する** Python ツール一式です。

```
 ┌──────────────┐   CAN 500kbps (11bit ID)   ┌──────────────────────┐
 │ PC Linux/Mac │ ── 0x06A 目標角度/要求 ──▶ │  Bluepill (STM32F103) │
 │  python-can  │ ◀── 0x069 現在角度 ─────── │  eXoCAN               │
 └──────────────┘                            └───┬──────────┬───────┘
                                                 │ SPI      │ GPIO
                                          エンコーダ×2   DCモータドライバ×2
                                          (14bit 絶対角)  (方向 + 駆動)
```

## 機構的な制限（可動範囲）

| 軸 | 可動範囲 |
|---|---|
| 軸1 | **180〜210°** |
| 軸2 | **100〜180°** |

この範囲の外へ目標角度を送ると、機構に無理な力がかかります。
- PC 側のツール（`jog.py`、`send_once_args.py`）は、この範囲の外を目標にしないようになっています。
  値は [python/can_bus.py](python/can_bus.py) の `AXIS_LIMITS` で一元管理しています。
- **ファームウェアには制限がありません。** ほかのツールや手作業で CAN フレームを送るときは、この範囲を守ってください。

## ディレクトリ構成

| パス | 内容 |
|---|---|
| [STM32duino/](STM32duino/) | Bluepill 用ファームウェア（PlatformIO / Arduino） |
| [STM32duino/src/main.cpp](STM32duino/src/main.cpp) | ファームウェア本体（1ファイル） |
| [python/](python/) | PC 側サンプルツール（python-can / SocketCAN） |
| [docs/](docs/) | 仕様・注意事項 |

## ドキュメント

- [docs/can-protocol.md](docs/can-protocol.md) — CAN メッセージ仕様（PC ⇔ マイコン）
- [STM32duino/README.md](STM32duino/README.md) — ファームウェアの構成・ピン・制御ロジック・ビルド方法
- [python/README.md](python/README.md) — Python ツールの使い方
- [docs/known-issues.md](docs/known-issues.md) — 既知の問題・注意点

## クイックスタート

1. **ファームウェアを書き込む**（ST-Link 使用）
   ```sh
   cd STM32duino
   pio run -t upload
   ```
2. **PC 側の準備**
   - Linux: `sudo ip link set can0 up type can bitrate 500000` と `pip install python-can`
   - macOS: candleLight などの USB-CAN をつなぎ、`python/` で venv を作って `pip install -r requirements.txt`、`brew install libusb`

   詳しくは [python/README.md](python/README.md) を参照してください。
3. **目標角度を送る**（軸1=200°, 軸2=150°。可動範囲内で指定）
   ```sh
   python3 python/send_once_args.py 200 150
   ```
4. **現在角度を定期的に問い合わせてモニタする**（4秒間隔）
   ```sh
   python3 python/monitor_and_ping.py 4
   ```
