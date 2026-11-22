"""The address phones on the same Wi-Fi can open, and its QR code (generated locally)."""

import io
import socket

import segno

_PROBE_ADDRESS = ("10.255.255.255", 1)
_LOOPBACK = "127.0.0.1"
QR_SCALE = 6


def lan_ip() -> str:
    """UDP connect() picks the outgoing interface without sending any packet."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(_PROBE_ADDRESS)
        address: str = probe.getsockname()[0]
    except OSError:
        address = _LOOPBACK
    finally:
        probe.close()
    return address


QR_BORDER = 2


def qr_svg(text: str) -> bytes:
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="svg", scale=QR_SCALE, border=QR_BORDER)
    return buffer.getvalue()


class LocalNetwork:
    def local_address(self) -> str:
        return lan_ip()

    def qr_svg(self, text: str) -> bytes:
        return qr_svg(text)
