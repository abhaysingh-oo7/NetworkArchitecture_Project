"""Independent client implementation of the BinaryHTTP/1.0 wire format."""

from __future__ import annotations

import socket
import struct


MAGIC = b"BH"
VERSION = 1
FRAME_TYPE_REQUEST = 0x01
FRAME_TYPE_RESPONSE = 0x02

FRAME_HEADER = struct.Struct("!2sBBBB2sI")
FRAME_HEADER_SIZE = FRAME_HEADER.size
MAX_FRAME_PAYLOAD = 16 * 1024 * 1024
MAX_HEADERS = 32
MAX_PATH_LENGTH = 4096
MAX_HEADER_VALUE_LENGTH = 65535

HEADER_NAMES = {
    1: "host",
    2: "accept",
    3: "content-type",
    4: "content-length",
    5: "connection",
    6: "server",
    7: "date",
    8: "cache-control",
    9: "content-encoding",
    10: "x-protocol",
}
HEADER_IDS = {name: ident for ident, name in HEADER_NAMES.items()}

HEADER_HOST = HEADER_IDS["host"]
HEADER_ACCEPT = HEADER_IDS["accept"]
HEADER_CONTENT_TYPE = HEADER_IDS["content-type"]
HEADER_CONTENT_LENGTH = HEADER_IDS["content-length"]
HEADER_CONNECTION = HEADER_IDS["connection"]
HEADER_SERVER = HEADER_IDS["server"]
HEADER_DATE = HEADER_IDS["date"]
HEADER_CACHE_CONTROL = HEADER_IDS["cache-control"]
HEADER_CONTENT_ENCODING = HEADER_IDS["content-encoding"]
HEADER_X_PROTOCOL = HEADER_IDS["x-protocol"]


class FrameError(ValueError):
    pass


def recv_exact(sock: socket.socket, size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            if not data:
                return None
            raise ConnectionError("connection closed mid-frame")
        data.extend(chunk)
    return bytes(data)


def _encode_headers(headers: dict[int, str]) -> bytes:
    if len(headers) > MAX_HEADERS:
        raise FrameError("too many headers")

    result = bytearray()
    for header_id, value in headers.items():
        if header_id not in HEADER_NAMES:
            raise FrameError("unknown header ID")

        value_bytes = value.encode("utf-8")
        if len(value_bytes) > MAX_HEADER_VALUE_LENGTH:
            raise FrameError("header value too long")

        result += struct.pack("!BH", header_id, len(value_bytes))
        result += value_bytes

    return bytes(result)


def build_request_frame(
    method: str,
    path: str,
    headers: dict[int, str] | None = None,
) -> bytes:
    if method != "GET":
        raise FrameError("only GET is supported")

    path_bytes = path.encode("utf-8")
    if not path_bytes or len(path_bytes) > MAX_PATH_LENGTH:
        raise FrameError("invalid path")

    # Method is represented by one byte: 1 = GET.
    payload = struct.pack("!BH", 1, len(path_bytes))
    payload += path_bytes
    payload += _encode_headers(headers or {})

    if len(payload) > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")

    header = FRAME_HEADER.pack(
        MAGIC,
        VERSION,
        FRAME_TYPE_REQUEST,
        0,
        len(headers or {}),
        b"\x00\x00",
        len(payload),
    )
    return header + payload


def _decode_headers(data: bytes, count: int) -> tuple[dict[int, str], int]:
    if count > MAX_HEADERS:
        raise FrameError("too many headers")

    offset = 0
    headers: dict[int, str] = {}

    for _ in range(count):
        if offset + 3 > len(data):
            raise FrameError("truncated header")

        header_id, length = struct.unpack_from("!BH", data, offset)
        offset += 3

        if offset + length > len(data):
            raise FrameError("truncated header value")

        value_bytes = data[offset : offset + length]
        offset += length

        if header_id not in HEADER_NAMES:
            # Unknown header IDs are safely skipped because their length
            # is explicitly encoded.
            continue

        try:
            value = value_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError("header is not UTF-8") from exc

        if header_id in headers:
            raise FrameError("duplicate header")

        headers[header_id] = value

    return headers, offset


def parse_response_frame(frame: bytes) -> dict:
    if len(frame) < FRAME_HEADER_SIZE:
        raise FrameError("response frame too short")

    (
        magic,
        version,
        frame_type,
        flags,
        header_count,
        reserved,
        payload_length,
    ) = FRAME_HEADER.unpack_from(frame)

    if magic != MAGIC or version != VERSION:
        raise FrameError("bad magic or version")
    if frame_type != FRAME_TYPE_RESPONSE:
        raise FrameError("not a response frame")
    if flags != 0 or reserved != b"\x00\x00":
        raise FrameError("unsupported flags/reserved bits")
    if payload_length > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")
    if len(frame) != FRAME_HEADER_SIZE + payload_length:
        raise FrameError("frame length mismatch")

    payload = frame[FRAME_HEADER_SIZE:]
    if len(payload) < 2:
        raise FrameError("missing status")

    status = struct.unpack_from("!H", payload, 0)[0]
    headers, consumed = _decode_headers(payload[2:], header_count)

    body_start = 2 + consumed
    body = payload[body_start:]

    return {
        "status": status,
        "headers": headers,
        "body": body,
    }


def recv_frame(sock: socket.socket) -> bytes | None:
    raw_header = recv_exact(sock, FRAME_HEADER_SIZE)
    if raw_header is None:
        return None

    (
        magic,
        version,
        frame_type,
        flags,
        header_count,
        reserved,
        payload_length,
    ) = FRAME_HEADER.unpack(raw_header)

    if magic != MAGIC or version != VERSION:
        raise FrameError("bad magic or version")
    if flags != 0 or reserved != b"\x00\x00":
        raise FrameError("unsupported flags/reserved bits")
    if payload_length > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")

    # Unknown future frame types can be skipped using payload_length.
    payload = recv_exact(sock, payload_length)
    if payload is None:
        raise ConnectionError("connection closed before payload")

    return raw_header + payload
