# BinaryHTTP/1.0 Protocol Specification

## 1. Purpose

BinaryHTTP/1.0 is a small HTTP-like application protocol carried over one
TCP connection. It is designed for this course project.

The protocol has two frame types:

- `0x01` — Request
- `0x02` — Response

A connection may carry multiple request/response frames without being closed.

## 2. Byte order

All multi-byte integer fields use **network byte order (big-endian)**.

## 3. Frame layout

Every frame starts with the same fixed-size 12-byte header:

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 2 | Magic | ASCII `BH` (`42 48`) |
| 2 | 1 | Version | `0x01` |
| 3 | 1 | Frame Type | `0x01` request, `0x02` response |
| 4 | 1 | Flags | Must be `0x00` in version 1 |
| 5 | 1 | Header Count | Number of encoded header entries |
| 6 | 2 | Reserved | Must be zero |
| 8 | 4 | Payload Length | Number of bytes after the fixed header |

The fixed header is always 12 bytes.

`Payload Length` makes the protocol self-framing. A receiver that encounters
a frame type it does not understand can read the 12-byte header and skip
exactly `Payload Length` bytes. This provides clean forward compatibility.

## 4. Request frame

The request payload is:

| Size | Field |
|---:|---|
| 1 | Method code |
| 2 | Path length |
| N | UTF-8 path |
| Remaining | Header block |

Version 1 defines:

- Method code `0x01` = `GET`

The path length is an unsigned 16-bit integer.

Example:

```text
01 00 0A 2F 69 6E 64 65 78 2E 68 74 6D 6C
```

means method `GET`, followed by a 10-byte path `/index.html`.

## 5. Response frame

The response payload is:

```text
Status (2 bytes)
Header block
Body bytes
```

Status is an unsigned 16-bit integer.

Examples:

- `200` — successful file response
- `400` — malformed/invalid request
- `404` — requested file does not exist
- `500` — server-side file/read failure

The body occupies all bytes remaining after the status and header block.

## 6. Header encoding

The protocol assigns numeric IDs to ten header names:

| ID | Header |
|---:|---|
| 1 | `host` |
| 2 | `accept` |
| 3 | `content-type` |
| 4 | `content-length` |
| 5 | `connection` |
| 6 | `server` |
| 7 | `date` |
| 8 | `cache-control` |
| 9 | `content-encoding` |
| 10 | `x-protocol` |

Each header entry is encoded as:

```text
Header ID     1 byte
Value Length  2 bytes
Value         N bytes
```

The value is UTF-8.

The frame header's `Header Count` says how many entries follow.

The length prefix means an implementation can skip an unknown header ID
without losing frame synchronization.

This deliberately uses two important ideas found in binary protocols:
numbered/typed fields and length-prefixed values.

## 7. File mapping

A request path is mapped below the server's configured document root.

For example:

```text
/index.html
```

maps to:

```text
www/index.html
```

A path may never escape the document root using `..`.

## 8. Connection behavior

The server keeps a TCP connection open after a valid request.

The intended sequence is:

```text
Client                         Server
  |                              |
  |---- Request Frame ---------->|
  |<--- Response Frame ----------|
  |                              |
  |---- Request Frame ---------->|
  |<--- Response Frame ----------|
  |                              |
```

The client must not open a second TCP connection for the same operation.

## 9. Malformed frames

The receiver must reject malformed frames rather than guessing their
meaning.

Examples include:

- wrong magic bytes
- unsupported version
- invalid flags/reserved bytes
- frame length mismatch
- truncated payload
- invalid UTF-8
- invalid path length
- too many headers

The server responds with `400 Bad Request` for malformed requests.

## 10. Client behavior

The command-line client supports:

```text
bcurl [-v] host:port/path
```

With `-v`, it prints hexadecimal representations of the complete request and
response frames.

The response body is written to stdout.

The client exits with a non-zero status for `4xx` and `5xx` responses.

## 11. Example

Command:

```bash
python3 client/client.py -v localhost:9000/index.html
```

The request contains:

```text
GET
/index.html
host: localhost:9000
accept: */*
```

The server returns:

```text
200
content-type: text/html
content-length: ...
connection: keep-alive
server: BinaryHTTP/1.0
x-protocol: BinaryHTTP/1.0
<body bytes>
```
