# can_bus.py
# CAN バスを開く共通処理（Linux: socketcan / macOS: gs_usb, slcan）
import argparse
import glob
import os
import sys
import time

import can

DEFAULT_INTERFACE = "socketcan" if sys.platform.startswith("linux") else "gs_usb"
DEFAULT_CHANNEL = {"socketcan": "can0", "gs_usb": "0"}

# 機構的な可動範囲 [deg]（目標角度はこの範囲に制限する）
AXIS_LIMITS = (
    (180, 210),  # 軸1
    (100, 180),  # 軸2
)

# Homebrew の libusb の場所（pyusb は標準ではここを探さない）
LIBUSB_CANDIDATES = [
    "/opt/homebrew/lib/libusb-1.0.dylib",  # Apple Silicon
    "/usr/local/lib/libusb-1.0.dylib",     # Intel Mac
]


def add_bus_args(parser: argparse.ArgumentParser):
    parser.add_argument("--interface", default=DEFAULT_INTERFACE,
                        choices=["socketcan", "gs_usb", "slcan"],
                        help=f"CAN interface (default: {DEFAULT_INTERFACE})")
    parser.add_argument("--channel", default=None,
                        help="socketcan: can0 / gs_usb: device index 0 / slcan: /dev/cu.usbmodemXXXX "
                             "(default: auto)")
    parser.add_argument("--iface", dest="channel", help=argparse.SUPPRESS)  # 旧オプション名
    parser.add_argument("--bitrate", type=int, default=500000, help="bitrate (default: 500000)")


def _load_libusb():
    """pyusb が Homebrew の libusb を見つけられるように先に読み込んでおく"""
    import usb.backend.libusb1 as libusb1
    if libusb1.get_backend() is not None:
        return
    for path in LIBUSB_CANDIDATES:
        if os.path.exists(path) and libusb1.get_backend(find_library=lambda _: path) is not None:
            return
    raise can.CanInitializationError("libusb not found. Install it with: brew install libusb")


def resolve_channel(interface: str, channel):
    if channel is not None:
        return channel
    if interface == "slcan":
        ports = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))
        if not ports:
            raise can.CanInitializationError("slcan device not found (/dev/cu.usbmodem*)")
        return ports[0]
    return DEFAULT_CHANNEL[interface]


def open_bus(args, retries: int = 3) -> can.BusABC:
    channel = resolve_channel(args.interface, args.channel)
    args.channel = channel

    if args.interface == "socketcan":
        # ビットレートは ip link 側で設定する
        return can.interface.Bus(interface="socketcan", channel=channel)

    if args.interface == "slcan":
        return can.interface.Bus(interface="slcan", channel=channel, bitrate=args.bitrate)

    # gs_usb: macOS ではまれに Access denied / I/O Error で開けないことがあるのでリトライする
    _load_libusb()
    last_err = None
    for _ in range(retries):
        try:
            return can.interface.Bus(interface="gs_usb", channel=int(channel), bitrate=args.bitrate)
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise can.CanInitializationError(f"failed to open gs_usb device {channel}: {last_err}")


def bus_label(args) -> str:
    """表示用の名前（例: can0 / gs_usb0 / slcan:/dev/cu.usbmodemXXXX）"""
    if args.interface == "socketcan":
        return args.channel
    if args.interface == "gs_usb":
        return f"gs_usb{args.channel}"
    return f"slcan:{args.channel}"
