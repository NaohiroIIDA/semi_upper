# jog.py
# キー入力で軸1・軸2を動かし、角度を記録して最大稼働範囲を求めるテストツール
#   A / S : 軸1 を -step / +step
#   Z / X : 軸2 を -step / +step
#   Space : 終了（その場で停止し、記録をまとめる）
import argparse
import csv
import os
import re
import select
import sys
import termios
import time
import tty
from datetime import datetime

import can

from can_bus import AXIS_LIMITS, add_bus_args, bus_label, open_bus

RX_ID = 0x69          # マイコン → PC
POLL_INTERVAL = 0.2   # 角度を問い合わせる間隔 [s]
STALL_MOVE = 2        # これ未満しか動かなければ「止まっている」とみなす [deg]
# ファームは受信フレームを1つしか保持できず、ループ（約50ms）ごとに処理する。
# 続けて送ると前のフレームが上書きされて消えるので、送信の間隔をあける [s]
MIN_TX_GAP = 0.1

# 矢印キーなどのエスケープシーケンス（例: ↑ = ESC [ A）
ESC_SEQ = re.compile(rb"\x1b(\[[0-9;?]*[ -/]*[@-~]|O.|.)?", re.S)
VALID_KEYS = "asxz "

KEYS = {
    "a": (0, -1), "s": (0, +1),
    "z": (1, -1), "x": (1, +1),
}


class Jog:
    def __init__(self, bus: can.BusABC, can_id: int):
        self.bus = bus
        self.can_id = can_id
        self.last_tx = 0.0

    def send(self, data):
        wait = self.last_tx + MIN_TX_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        self.last_tx = time.time()
        self.bus.send(can.Message(arbitration_id=self.can_id, is_extended_id=False, data=data))

    def read_pos(self, timeout=0.3):
        """cmd=9 で現在角度を問い合わせる。応答がなければ None"""
        self.send([9, 0, 0, 0, 0, 255, 255, 255])
        end = time.time() + timeout
        while time.time() < end:
            m = self.bus.recv(timeout=0.05)
            # gs_usb は自分の送信をエコーで返すので is_rx で除外する
            if m is not None and m.is_rx and m.arbitration_id == RX_ID and len(m.data) >= 5:
                return [m.data[1] * 256 + m.data[2], m.data[3] * 256 + m.data[4]]
        return None

    def set_target(self, tgt):
        t1, t2 = tgt
        self.send([1, t1 >> 8, t1 & 0xFF, t2 >> 8, t2 & 0xFF, 255, 255, 255])

    def hold(self):
        """cmd=0: 現在位置を目標にする（モータ停止）"""
        self.send([0, 0, 0, 0, 0, 255, 255, 255])

    def drain(self, sec=0.3):
        end = time.time() + sec
        while time.time() < end:
            self.bus.recv(timeout=0.05)


def read_keys(fd):
    """溜まっている入力をすべて読み、有効なキー（a/s/z/x/スペース）だけを返す。
    矢印キーなどのエスケープシーケンスや、日本語入力などのそれ以外の文字は捨てる"""
    data = b""
    while select.select([fd], [], [], 0)[0]:
        chunk = os.read(fd, 1024)
        if not chunk:
            break
        data += chunk
    data = ESC_SEQ.sub(b"", data)
    return [c for c in data.decode("ascii", errors="ignore").lower() if c in VALID_KEYS]


def limit_target(axis, cur, delta):
    """目標角度を機構的な可動範囲に収める。(新しい目標, 制限にかかったか) を返す。
    範囲外にいるときは、範囲に戻る向きの操作だけを受け付ける"""
    lo, hi = AXIS_LIMITS[axis]
    want = cur + delta
    new = max(lo, min(hi, want))
    if (new - cur) * delta < 0:  # 範囲外からさらに外へ出る操作
        new = cur
    return new, new != want


def main():
    ap = argparse.ArgumentParser(description="Jog axis 1 (A/S) and axis 2 (Z/X), record angles. Space to quit.")
    ap.add_argument("--step", type=int, default=5, help="degrees per key press (default: 5)")
    ap.add_argument("--stall", type=float, default=3.0,
                    help="hold if an axis does not move toward target for this many seconds (default: 3.0, 0=off)")
    ap.add_argument("--log", default=None, help="CSV log file (default: jog_YYYYmmdd_HHMMSS.csv)")
    ap.add_argument("--id", type=lambda x: int(x, 0), default=0x6a, help="TX CAN ID (default: 0x6a)")
    add_bus_args(ap)
    args = ap.parse_args()

    if not sys.stdin.isatty():
        print("jog.py needs a terminal (TTY).")
        sys.exit(1)

    log_path = args.log or datetime.now().strftime("jog_%Y%m%d_%H%M%S.csv")

    try:
        bus = open_bus(args)
    except can.CanError as e:
        print("open failed:", e)
        sys.exit(2)

    jog = Jog(bus, args.id)
    pos = jog.read_pos(timeout=1.0)
    if pos is None:
        print("no reply from device (ID 0x069). Check power and wiring.")
        bus.shutdown()
        sys.exit(2)

    tgt = list(pos)
    pmin, pmax = list(pos), list(pos)
    stall_ref = [(pos[0], time.time()), (pos[1], time.time())]  # 停止判定の基準（角度, 時刻）
    events = []
    t0 = time.time()

    fd = sys.stdin.fileno()
    old_tty = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    print(f"Connected: {bus_label(args)}  start pos: axis1={pos[0]} axis2={pos[1]}  step={args.step}")
    print("A/S: axis1 -/+   Z/X: axis2 -/+   Space: quit")
    print(f"Limits: axis1 {AXIS_LIMITS[0][0]}..{AXIS_LIMITS[0][1]}  axis2 {AXIS_LIMITS[1][0]}..{AXIS_LIMITS[1][1]}")
    for i in range(2):
        lo, hi = AXIS_LIMITS[i]
        if not lo <= pos[i] <= hi:
            print(f"WARNING: axis{i + 1} is out of range ({pos[i]}). Only moves toward the range are accepted.")
    print(f"Logging to {log_path}\n")

    with open(log_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "pos1", "pos2", "tgt1", "tgt2", "event"])
        w.writerow([0.0, pos[0], pos[1], tgt[0], tgt[1], "start"])
        try:
            next_poll = time.time()
            resend = False
            event = ""  # 次に CSV へ書く出来事（書いたら空にする）
            while True:

                # キー入力（溜まっている分をまとめて処理）
                quit_req = False
                moved = False
                for k in read_keys(fd):
                    if k == " ":
                        quit_req = True
                        break
                    else:
                        axis, sign = KEYS[k]
                        new, limited = limit_target(axis, tgt[axis], sign * args.step)
                        if limited:
                            lo, hi = AXIS_LIMITS[axis]
                            event = (event + " " if event else "") + f"LIMIT axis{axis + 1} ({lo}..{hi})"
                        if new != tgt[axis]:
                            tgt[axis] = new
                            stall_ref[axis] = (pos[axis], time.time())
                            moved = True
                if quit_req:
                    break
                if moved:
                    jog.set_target(tgt)
                    resend = True
                    event = (event + " " if event else "") + f"target {tgt[0]},{tgt[1]}"

                # 角度の取得と記録
                if time.time() >= next_poll:
                    next_poll = time.time() + POLL_INTERVAL
                    if resend:
                        # 取りこぼし対策で目標をもう一度送る（同じ値なので副作用なし）
                        jog.set_target(tgt)
                        resend = False
                    p = jog.read_pos()
                    if p is None:
                        event = (event + " " if event else "") + "no reply"
                    else:
                        pos = p
                        for i in range(2):
                            pmin[i] = min(pmin[i], pos[i])
                            pmax[i] = max(pmax[i], pos[i])

                        # 停止判定: 目標に届いていないのに一定時間ほとんど動かない → 端に当たったとみなして停止
                        if args.stall > 0:
                            for i in range(2):
                                if abs(pos[i] - tgt[i]) < 5 or abs(pos[i] - stall_ref[i][0]) >= STALL_MOVE:
                                    stall_ref[i] = (pos[i], time.time())
                                elif time.time() - stall_ref[i][1] > args.stall:
                                    jog.hold()
                                    tgt = list(pos)
                                    stall_ref = [(pos[0], time.time()), (pos[1], time.time())]
                                    msg = f"STALL axis{i + 1} at {pos[i]} -> hold"
                                    events.append(msg)
                                    event = (event + " " if event else "") + msg
                                    print(f"\r\033[K{msg}")
                                    break

                    w.writerow([round(time.time() - t0, 2), pos[0], pos[1], tgt[0], tgt[1], event])
                    event = ""
                    print(f"\r\033[Kaxis1 {pos[0]:3d} -> {tgt[0]:3d}  [{pmin[0]:3d}..{pmax[0]:3d}]   "
                          f"axis2 {pos[1]:3d} -> {tgt[1]:3d}  [{pmin[1]:3d}..{pmax[1]:3d}]", end="", flush=True)

                time.sleep(0.01)
        except KeyboardInterrupt:
            pass
        finally:
            # 必ず停止してから閉じる
            try:
                jog.hold()
                time.sleep(0.3)
                last = jog.read_pos()
                if last is not None:
                    pos = last
                jog.drain()
            except can.CanError:
                pass
            termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
            bus.shutdown()
            w.writerow([round(time.time() - t0, 2), pos[0], pos[1], pos[0], pos[1], "end (hold)"])

    summary = [
        f"Duration: {time.time() - t0:.1f} s",
        f"axis1: min={pmin[0]:3d}  max={pmax[0]:3d}  range={pmax[0] - pmin[0]:3d} deg",
        f"axis2: min={pmin[1]:3d}  max={pmax[1]:3d}  range={pmax[1] - pmin[1]:3d} deg",
        f"final: axis1={pos[0]} axis2={pos[1]}",
    ] + [f"event: {e}" for e in events]
    summary_path = os.path.splitext(log_path)[0] + "_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(summary) + "\n")

    print("\n\n=== Range of motion ===")
    print("\n".join(summary))
    print(f"\nLog: {log_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
