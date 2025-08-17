# can_monitor_and_ping.py
import argparse
import threading
import time
import sys
import os
import termios
import tty

import can

TX_PAYLOAD = bytes([9, 0, 0, 0, 0, 255, 255, 255])

def format_candump_line(iface: str, msg: can.Message) -> str:
    ts = time.time()
    data_hex = " ".join(f"{b:02X}" for b in msg.data)
    return f"({ts:.6f}) {iface}  {msg.arbitration_id:03X}   [{len(msg.data)}]  {data_hex}"

class KeyWatcher:
    """端末で何かキーが押されたら stop_event を立てる"""
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.fd = None
        self.old = None
        self.thread = None

    def start(self):
        if sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)  # 1文字で反応
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            print("Press any key to stop.")
        else:
            print("stdin is not a TTY. Use Ctrl+C to stop.")

    def _run(self):
        try:
            os.read(self.fd, 1)  # 1文字読むまでブロック
            self.stop_event.set()
        except Exception:
            pass

    def restore(self):
        if self.fd is not None and self.old is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

def sender_loop(bus: can.BusABC, can_id: int, iface: str, interval: float, stop_event: threading.Event):
    msg = can.Message(arbitration_id=can_id, is_extended_id=False, data=TX_PAYLOAD)
    while not stop_event.is_set():
        try:
            bus.send(msg, timeout=0.2)
            print(f"TX -> {iface}  {can_id:03X}   [{len(TX_PAYLOAD)}]  " +
                  " ".join(f"{b:02X}" for b in TX_PAYLOAD))
        except can.CanError as e:
            print("TX failed:", e)
        # 早期終了に反応できるように wait を使用
        if stop_event.wait(interval):
            break

def main():
    ap = argparse.ArgumentParser(description="SocketCAN monitor (candump-like) + periodic TX")
    ap.add_argument("interval", type=float, help="TX interval seconds (e.g., 1.0)")
    ap.add_argument("--iface", default="can0", help="SocketCAN interface (default: can0)")
    ap.add_argument("--id", type=lambda x: int(x, 0), default=0x6a, help="TX CAN ID (default: 0x6a)")
    args = ap.parse_args()

    # CANバスに接続
    bus = can.interface.Bus(channel=args.iface, interface="socketcan")

    stop_event = threading.Event()

    # 任意キー監視開始
    keywatch = KeyWatcher(stop_event)
    keywatch.start()

    # 送信スレッド開始
    tx_thread = threading.Thread(
        target=sender_loop,
        args=(bus, args.id, args.iface, args.interval, stop_event),
        daemon=True,
    )
    tx_thread.start()

    print(f"Monitoring {args.iface}. Receiving like candump; sending to ID 0x{args.id:03X} every {args.interval}s.")
    try:
        while not stop_event.is_set():
            # 受信（タイムアウト短めでポーリング）
            msg = bus.recv(timeout=0.2)
            if msg is not None:
                # candump 風表示（IDと8ビットデータ）
                print(format_candump_line(args.iface, msg))
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        stop_event.set()
        tx_thread.join(timeout=1.0)
        bus.shutdown()
        keywatch.restore()
        print("Bye.")

if __name__ == "__main__":
    main()
