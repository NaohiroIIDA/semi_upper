# Python によるサンプルプログラム

## python-canインストール
pip install python-can

## CANインターフェース
sudo ip link set can0 up type can bitrate 500000

## サンプル１：　角度データ送出
send_once_args.py 角度1 角度2--id アドレス
アドレスに角度設定値を1回送信する

`python3 send_once_args.py 220 90 --id 0x6a`


## サンプル2：　角度問い合わせ
monitor_and_ping.py　インターバル（秒）

`python3 monitor_and_ping.py　4`


