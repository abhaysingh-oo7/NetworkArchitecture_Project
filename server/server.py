#!/usr/bin/env python3
"""Binary HTTP server for the course project."""

from __future__ import annotations

import argparse
import mimetypes
import os
import socket
import struct
from pathlib import Path

from protocol import (
    FrameError,
    FRAME_TYPE_REQUEST,
    FRAME_TYPE_RESPONSE,
    HEADER_CONNECTION,
    HEADER_CONTENT_LENGTH,
    HEADER_CONTENT_TYPE,
    HEADER_SERVER,
    HEADER_X_PROTOCOL,
    MAX_FRAME_PAYLOAD,
    build_response_frame,
    parse_request_frame,
    recv_exact,
    recv_frame,
)


SERVER_NAME = "BinaryHTTP/1.0"


def safe_file_path(root: Path, request_path: str) -> Path | None:
    """Map a URL path below root without allowing path traversal."""
    if not request_path.startswith("/"):
        return None

    # Ignore query/fragment for file lookup.
    clean_path = request_path.split("?", 1)[0].split("#", 1)[0]
    if not clean_path:
        clean_path = "/"

    relative = clean_path.lstrip("/")
    if relative == "":
        relative = "index.html"

    candidate = (root / relative).resolve()

    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None

    return candidate


def make_error(status: int, message: str, keep_alive: bool) -> bytes:
    body = (message + "\n").encode("utf-8")
    headers = {
        HEADER_CONTENT_TYPE: "text/plain; charset=utf-8",
        HEADER_CONTENT_LENGTH: str(len(body)),
        HEADER_CONNECTION: "keep-alive" if keep_alive else "close",
        HEADER_SERVER: SERVER_NAME,
        HEADER_X_PROTOCOL: "BinaryHTTP/1.0",
    }
    return build_response_frame(status, headers, body)


def handle_request(frame: bytes, root: Path) -> bytes:
    """Parse one request frame and produce exactly one response frame."""
    try:
        request = parse_request_frame(frame)
    except FrameError:
        return make_error(400, "Bad Request", True)

    if request["method"] != "GET":
        return make_error(400, "Bad Request", True)

    path = request["path"]
    file_path = safe_file_path(root, path)

    if file_path is None:
        return make_error(400, "Bad Request", True)

    if not file_path.is_file():
        return make_error(404, "Not Found", True)

    try:
        body = file_path.read_bytes()
    except OSError:
        return make_error(500, "Internal Server Error", True)

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    headers = {
        HEADER_CONTENT_TYPE: content_type,
        HEADER_CONTENT_LENGTH: str(len(body)),
        HEADER_CONNECTION: "keep-alive",
        HEADER_SERVER: SERVER_NAME,
        HEADER_X_PROTOCOL: "BinaryHTTP/1.0",
    }
    return build_response_frame(200, headers, body)


def serve_connection(conn: socket.socket, root: Path, verbose: bool = False) -> None:
    """Serve multiple request/response frames on one TCP connection."""
    with conn:
        while True:
            try:
                frame = recv_frame(conn)
            except FrameError:
                # A malformed frame whose boundary cannot be trusted cannot be
                # safely followed by another frame. Close the connection.
                # Malformed request payloads with a valid frame boundary are
                # handled as HTTP 400 by handle_request().
                return
            except (ConnectionError, OSError):
                return

            if frame is None:
                return

            if verbose:
                print(f"[server] received {len(frame)} bytes")

            frame_type = frame[3]
            if frame_type != FRAME_TYPE_REQUEST:
                # The fixed header contains the complete payload length, so an
                # unknown frame type can be skipped without losing sync.
                if verbose:
                    print(f"[server] skipped unknown frame type 0x{frame_type:02x}")
                continue

            response = handle_request(frame, root)

            try:
                conn.sendall(response)
            except OSError:
                return

            if verbose:
                print(f"[server] sent {len(response)} bytes")


def run_server(host: str, port: int, root: Path, verbose: bool) -> None:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Document root does not exist: {root}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(16)

        print(f"Binary HTTP server listening on {host}:{port}")
        print(f"Document root: {root}")

        while True:
            try:
                conn, address = server.accept()
            except KeyboardInterrupt:
                print("\nServer stopped.")
                return

            if verbose:
                print(f"[server] connection from {address}")

            try:
                serve_connection(conn, root, verbose)
            except Exception as exc:
                if verbose:
                    print(f"[server] connection error: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Custom binary HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent / "www",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    run_server(args.host, args.port, args.root, args.verbose)


if __name__ == "__main__":
    main()
