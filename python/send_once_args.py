# send_once_args.py
import argparse
import sys
import can

def to_u16_be_bytes(n: int):
    if not (0 <= n <= 360):
        raise ValueError(f"value out of range (0..360): {n}")
    return (n >> 8) & 0xFF, n & 0xFF  # 上位, 下位

def main():
    p = argparse.ArgumentParser(description="Send one CAN frame with two angles (0..360).")
    p.add_argument("arg1", type=int, help="first value (0..360)")
    p.add_argument("arg2", type=int, help="second value (0..360)")
    p.add_argument("--iface", default="can0", help="SocketCAN interface (default: can0)")
    p.add_argument("--id", type=lambda x: int(x, 0), default=0x69, help="CAN ID (default: 0x69)")
    args = p.parse_args()

    try:
        a1_hi, a1_lo = to_u16_be_bytes(args.arg1)
        a2_hi, a2_lo = to_u16_be_bytes(args.arg2)
    except ValueError as e:
        print(e)
        sys.exit(1)

    payload = bytes([1, a1_hi, a1_lo, a2_hi, a2_lo, 255, 255, 255])

    # can0 に接続
    # bus = can.interface.Bus(channel=args.iface, bustype="socketcan")
    bus = can.interface.Bus(channel=args.iface, interface="socketcan", bitrate=500000)

    msg = can.Message(arbitration_id=args.id, is_extended_id=False, data=payload)

    try:
        bus.send(msg, timeout=0.5)
        print("sent OK")
    except can.CanError as e:
        print("send failed:", e)
        sys.exit(2)
    finally:
        bus.shutdown()

    # 結果表示
    print(f"iface={args.iface} id=0x{args.id:03X}")
    print(f"arg1={args.arg1} -> bytes [{a1_hi:02X} {a1_lo:02X}]")
    print(f"arg2={args.arg2} -> bytes [{a2_hi:02X} {a2_lo:02X}]")
    print("payload (hex):", payload.hex(" "))

if __name__ == "__main__":
    main()
