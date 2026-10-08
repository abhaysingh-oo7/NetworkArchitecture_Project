#!/usr/bin/env python3
"""curl-like command-line client for BinaryHTTP/1.0."""

from __future__ import annotations

import argparse
import socket
import sys

from protocol import (
    FrameError,
    FRAME_HEADER_SIZE,
    FRAME_TYPE_RESPONSE,
    HEADER_CONTENT_LENGTH,
    HEADER_NAMES,
    build_request_frame,
    parse_response_frame,
    recv_frame,
)


def hexdump(data: bytes) -> str:
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{offset:04x}  {hex_part:<47}  {ascii_part}")
    return "\n".join(lines)


def parse_target(target: str) -> tuple[str, int, str]:
    if "://" in target:
        scheme, target = target.split("://", 1)
        if scheme != "http":
            raise ValueError("only http:// targets are supported")

    if "/" not in target:
        authority = target
        path = "/"
    else:
        authority, path = target.split("/", 1)
        path = "/" + path

    if ":" in authority:
        host, port_text = authority.rsplit(":", 1)
        port = int(port_text)
    else:
        host = authority
        port = 9000

    if not host:
        raise ValueError("missing host")

    return host, port, path


def run_client(target: str, verbose: bool) -> int:
    try:
        host, port, path = parse_target(target)
        request = build_request_frame(
            "GET",
            path,
            {
                1: f"{host}:{port}",  # Host
                2: "*/*",             # Accept
            },
        )
    except (ValueError, FrameError) as exc:
        print(f"bcurl: {exc}", file=sys.stderr)
        return 2

    if verbose:
        print("> BinaryHTTP request")
        print(hexdump(request))

    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            # One TCP connection is opened and reused for this request.
            sock.sendall(request)

            response_frame = recv_frame(sock)
            if response_frame is None:
                raise ConnectionError("server closed the connection")

            if verbose:
                print("< BinaryHTTP response")
                print(hexdump(response_frame))

            response = parse_response_frame(response_frame)

            body = response["body"]
            content_length = response["headers"].get(HEADER_CONTENT_LENGTH)

            if content_length is not None and int(content_length) != len(body):
                raise FrameError("response Content-Length mismatch")

            sys.stdout.buffer.write(body)
            if body and not body.endswith(b"\n"):
                sys.stdout.buffer.write(b"\n")

            status = response["status"]
            if verbose:
                print(
                    f"\n[status={status}, body={len(body)} bytes]",
                    file=sys.stderr,
                )

            return 0 if status < 400 else 1

    except (OSError, ConnectionError, FrameError, ValueError) as exc:
        print(f"bcurl: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bcurl",
        description="Client for the BinaryHTTP/1.0 course protocol",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("url", help="for example: localhost:9000/index.html")
    args = parser.parse_args()

    raise SystemExit(run_client(args.url, args.verbose))


if __name__ == "__main__":
    main()
