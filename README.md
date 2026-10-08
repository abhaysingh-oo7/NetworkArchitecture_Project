# HTTP in Binary — Two Tracks, One Protocol

This project implements a small HTTP-like protocol over a single persistent TCP connection. The protocol is binary instead of text-based, but it keeps the same core ideas as HTTP: requests, responses, paths, headers, status codes, and document serving.

The important idea is that the protocol is defined by a shared specification, not by shared code. The client and server each implement the same wire format independently.

## What this project is

The project demonstrates a minimal network protocol in which:

- the client sends a binary request frame
- the server parses the request
- the server maps the URL path to files under a document root
- the server sends a binary response frame
- the client reads the response and writes the body to stdout
- the same TCP socket can be reused for multiple requests

This is intentionally a small protocol used for learning: fixed-size frames, explicit payload lengths, numbered header fields, and length-prefixed values.

## Project structure

```text
http-binary-project/
├── README.md
├── spec.md
├── hexdump.md
├── client/
│   ├── bcurl
│   ├── client.py
│   └── protocol.py
├── server/
│   ├── bserve
│   ├── server.py
│   ├── protocol.py
│   └── www/
│       ├── index.html
│       ├── style.css
│       └── script.js
└──
```

## Deliverables required by the course

The course image says that the hand-in is not just “a program.” The real deliverables are:

1. A protocol specification that clearly explains the binary wire format.
2. A working implementation of the client and server.
3. An annotated dump of a complete request and response frame so the bytes are understandable.

That is why the repo contains:

- [spec.md](spec.md) — the protocol specification
- [hexdump.md](hexdump.md) — an annotated raw-byte example
- [README.md](README.md) — project overview and usage
- [server/](server/) — server implementation
- [client/](client/) — client implementation

If you cannot annotate your own bytes, the spec is not finished.

## Protocol overview

The protocol uses a fixed 12-byte frame header:

- 2-byte magic: `BH`
- 1-byte version: `0x01`
- 1-byte frame type: request or response
- 1-byte flags: must be zero
- 1-byte header count
- 2-byte reserved field: must be zero
- 4-byte payload length

This design is important because the payload length allows the receiver to skip unknown future frame types without losing synchronization.

### Request frame

A request frame contains:

- method code
- path length
- UTF-8 path bytes
- header block

Version 1 supports:

- method code `0x01` = `GET`

### Response frame

A response frame contains:

- 2-byte status code
- header block
- body bytes

Supported status codes include:

- `200` OK
- `400` Bad Request
- `404` Not Found
- `500` Internal Server Error

### Header encoding

Headers use numeric IDs instead of plain text names. This makes the protocol more compact and easier to parse while preserving extensibility. Each header entry is encoded as:

- 1-byte header ID
- 2-byte value length
- N bytes of UTF-8 header value

## Connection behavior

The server keeps the TCP connection open after serving a valid request. The same connection can be used for multiple request/response exchanges. The client must not open a second TCP connection for the same operation.

This is one of the key protocol properties the assignment is testing.

## Requirements

- Python 3.10+
- No external Python packages required

## Running the project

### Start the server

From the `server` directory:

```bash
cd server
./bserve ./www 9000
```

Equivalent Python form:

```bash
python3 server/server.py --root ./www --port 9000
```

### Run the client

From the `client` directory:

```bash
cd client
./bcurl localhost:9000/index.html
```

To print the full binary request and response as hex:

```bash
./bcurl -v localhost:9000/index.html
```

The client prints the response body to stdout and exits non-zero for `4xx` and `5xx` responses.

## Example requests and responses

A basic request looks like this conceptually:

```text
GET /index.html
host: localhost:9000
accept: */*
```

The actual protocol sends this as a binary frame, not as plain HTTP text.

A successful response includes:

- status code
- content-type
- content-length
- connection
- server
- x-protocol
- body bytes

Examples from the project are documented in [spec.md](spec.md) and [hexdump.md](hexdump.md).

## Error handling

Malformed frames are rejected rather than guessed at. Invalid requests return `400 Bad Request`.

Missing files return `404 Not Found`.

File read failures return `500 Internal Server Error`.

## Security and correctness constraints

The implementation also enforces important protocol rules:

- path traversal is prevented
- invalid UTF-8 is rejected
- frame length mismatches are rejected
- unknown headers can be skipped safely because their lengths are known
- a malformed frame cannot be interpreted without a proper boundary

## Summary

This project is not a standard HTTP implementation. It is a deliberately small, custom binary protocol over TCP that teaches the core ideas behind framed, length-prefixed communication. The real strength of the submission is not that it “looks like HTTP,” but that it defines a precise binary protocol and proves it with both working code and an annotated byte dump.

The project is complete when:

- the spec explains the bytes,
- the code implements the spec,
- the hexdump proves the bytes match the description.

That combination is what the course image is asking for.
