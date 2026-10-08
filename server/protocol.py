"""BinaryHTTP/1.0 wire-format implementation for the server side."""

from __future__ import annotations

import socket
import struct


MAGIC = b"BH"
VERSION = 1

FRAME_TYPE_REQUEST = 0x01
FRAME_TYPE_RESPONSE = 0x02

# Fixed-size frame header:
# magic(2) version(1) type(1) flags(1) header_count(1)
# reserved(2) payload_length(4) = 12 bytes.
FRAME_HEADER = struct.Struct("!2sBBBB2sI")
FRAME_HEADER_SIZE = FRAME_HEADER.size

MAX_FRAME_PAYLOAD = 16 * 1024 * 1024
MAX_HEADERS = 32
MAX_PATH_LENGTH = 4096
MAX_HEADER_VALUE_LENGTH = 65535

# Exactly ten protocol header names are assigned numeric IDs.
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
    """Raised when a binary frame is malformed."""


def recv_exact(sock: socket.socket, size: int) -> bytes | None:
    if size < 0:
        raise FrameError("negative read size")
    if size == 0:
        return b""

    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            if not chunks:
                return None
            raise ConnectionError("connection closed mid-frame")
        chunks.extend(chunk)
    return bytes(chunks)


def _encode_headers(headers: dict[int, str]) -> bytes:
    if len(headers) > MAX_HEADERS:
        raise FrameError("too many headers")

    encoded = bytearray()
    for header_id, value in headers.items():
        if header_id not in HEADER_NAMES:
            raise FrameError("unknown header ID")
        value_bytes = value.encode("utf-8")
        if len(value_bytes) > MAX_HEADER_VALUE_LENGTH:
            raise FrameError("header value too long")

        encoded += struct.pack("!BH", header_id, len(value_bytes))
        encoded += value_bytes

    return bytes(encoded)


def _decode_headers(data: bytes, count: int) -> dict[int, str]:
    if count > MAX_HEADERS:
        raise FrameError("too many headers")

    headers: dict[int, str] = {}
    offset = 0

    for _ in range(count):
        if offset + 3 > len(data):
            raise FrameError("truncated header")

        header_id, value_length = struct.unpack_from("!BH", data, offset)
        offset += 3

        if header_id not in HEADER_NAMES:
            # This protocol version cannot safely interpret the field.
            # Because the field is length-prefixed, it can be skipped.
            offset += value_length
            if offset > len(data):
                raise FrameError("truncated unknown header")
            continue

        if offset + value_length > len(data):
            raise FrameError("truncated header value")

        try:
            value = data[offset : offset + value_length].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError("header is not valid UTF-8") from exc

        if header_id in headers:
            raise FrameError("duplicate header")

        headers[header_id] = value
        offset += value_length

    if offset != len(data):
        raise FrameError("unexpected bytes in header block")

    return headers


def build_request_frame(
    method: str,
    path: str,
    headers: dict[int, str] | None = None,
) -> bytes:
    if method != "GET":
        raise FrameError("only GET is supported")

    path_bytes = path.encode("utf-8")
    if not path_bytes or len(path_bytes) > MAX_PATH_LENGTH:
        raise FrameError("invalid path length")

    header_map = headers or {}
    header_block = _encode_headers(header_map)

    payload = (
        struct.pack("!BH", 1, len(path_bytes))
        + path_bytes
        + header_block
    )

    if len(payload) > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")

    header = FRAME_HEADER.pack(
        MAGIC,
        VERSION,
        FRAME_TYPE_REQUEST,
        0,
        len(header_map),
        b"\x00\x00",
        len(payload),
    )
    return header + payload


def parse_request_frame(frame: bytes) -> dict:
    if len(frame) < FRAME_HEADER_SIZE:
        raise FrameError("frame too short")

    magic, version, frame_type, flags, header_count, reserved, payload_length = (
        FRAME_HEADER.unpack_from(frame)
    )

    if magic != MAGIC or version != VERSION:
        raise FrameError("bad magic or version")
    if frame_type != FRAME_TYPE_REQUEST:
        raise FrameError("not a request frame")
    if flags != 0 or reserved != b"\x00\x00":
        raise FrameError("unsupported flags/reserved bits")
    if payload_length > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")
    if len(frame) != FRAME_HEADER_SIZE + payload_length:
        raise FrameError("frame length mismatch")

    payload = frame[FRAME_HEADER_SIZE:]
    if len(payload) < 3:
        raise FrameError("request payload too short")

    method_length, path_length = struct.unpack_from("!BH", payload)
    offset = 3

    if method_length != 1 or offset + path_length > len(payload):
        raise FrameError("invalid request path")

    # This version uses the one-byte method code 1 = GET.
    method_code = payload[0]
    if method_code != 1:
        raise FrameError("unsupported method")

    path_bytes = payload[offset : offset + path_length]
    offset += path_length

    try:
        path = path_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrameError("path is not valid UTF-8") from exc

    headers = _decode_headers(payload[offset:], header_count)

    return {
        "method": "GET",
        "path": path,
        "headers": headers,
    }


def build_response_frame(
    status: int,
    headers: dict[int, str],
    body: bytes,
) -> bytes:
    if not 100 <= status <= 599:
        raise FrameError("invalid status")

    header_block = _encode_headers(headers)
    payload = struct.pack("!H", status) + header_block + body

    if len(payload) > MAX_FRAME_PAYLOAD:
        raise FrameError("response too large")

    header = FRAME_HEADER.pack(
        MAGIC,
        VERSION,
        FRAME_TYPE_RESPONSE,
        0,
        len(headers),
        b"\x00\x00",
        len(payload),
    )
    return header + payload


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

    # Any future frame type can be skipped safely because payload_length
    # tells the receiver exactly how many bytes belong to this frame.
    if payload_length > MAX_FRAME_PAYLOAD:
        raise FrameError("payload too large")

    payload = recv_exact(sock, payload_length)
    if payload is None:
        raise ConnectionError("connection closed before payload")

    return raw_header + payload
