# send_once_args.py
import argparse
import sys
import time

import can

from can_bus import add_bus_args, open_bus

def to_u16_be_bytes(n: int):
    if not (0 <= n <= 360):
        raise ValueError(f"value out of range (0..360): {n}")
    return (n >> 8) & 0xFF, n & 0xFF  # 上位, 下位

def wait_echo(bus: can.BusABC, can_id: int, timeout: float) -> bool:
    """自分の送信フレームのエコーが返るまで待つ（gs_usb 用）"""
    end = time.time() + timeout
    while time.time() < end:
        m = bus.recv(timeout=0.1)
        if m is not None and not m.is_rx and m.arbitration_id == can_id:
            return True
    return False

def main():
    p = argparse.ArgumentParser(description="Send one CAN frame with two angles (0..360).")
    p.add_argument("arg1", type=int, help="first value (0..360)")
    p.add_argument("arg2", type=int, help="second value (0..360)")
    p.add_argument("--id", type=lambda x: int(x, 0), default=0x6a, help="CAN ID (default: 0x6a)")
    add_bus_args(p)
    args = p.parse_args()

    try:
        a1_hi, a1_lo = to_u16_be_bytes(args.arg1)
        a2_hi, a2_lo = to_u16_be_bytes(args.arg2)
    except ValueError as e:
        print(e)
        sys.exit(1)

    payload = bytes([1, a1_hi, a1_lo, a2_hi, a2_lo, 255, 255, 255])

    try:
        bus = open_bus(args)
    except can.CanError as e:
        print("open failed:", e)
        sys.exit(2)

    msg = can.Message(arbitration_id=args.id, is_extended_id=False, data=payload)

    try:
        bus.send(msg, timeout=0.5)
        if args.interface == "gs_usb":
            # gs_usb は送信完了（相手の ACK）をエコーで返す。
            # エコーを読まずに閉じるとアダプタが詰まるので、受け取ってから閉じる
            if not wait_echo(bus, msg.arbitration_id, timeout=1.0):
                print("send failed: no ACK (is the device on the bus?)")
                sys.exit(2)
        print("sent OK")
    except can.CanError as e:
        print("send failed:", e)
        sys.exit(2)
    finally:
        bus.shutdown()

    # 結果表示
    print(f"interface={args.interface} channel={args.channel} id=0x{args.id:03X}")
    print(f"arg1={args.arg1} -> bytes [{a1_hi:02X} {a1_lo:02X}]")
    print(f"arg2={args.arg2} -> bytes [{a2_hi:02X} {a2_lo:02X}]")
    print("payload (hex):", payload.hex(" "))

if __name__ == "__main__":
    main()
