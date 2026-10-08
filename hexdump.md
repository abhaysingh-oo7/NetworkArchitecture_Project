# Annotated Request and Response Hexdump

Run the server first:

```bash
python3 server/server.py --port 9000
```

Then run:

```bash
python3 client/client.py -v localhost:9000/index.html
```

The client prints a complete request and response frame.

## Request frame structure

The first 12 bytes are the fixed frame header:

```text
42 48 01 01 00 02 00 00 00 00 00 XX
│  │  │  │  │  │  │  │        └──── payload length
│  │  │  │  │  │  └──┴──────────── reserved
│  │  │  │  │  └─────────────────── header count = 2
│  │  │  │  └────────────────────── flags = 0
│  │  │  └───────────────────────── frame type = request
│  │  └──────────────────────────── version = 1
└──┴──────────────────────────────── magic = "BH"
```

The exact payload-length bytes depend on the request.

The payload begins:

```text
01 00 0B 2F 69 6E 64 65 78 2E 68 74 6D 6C
│  └───┬──┘ └─────────────── path ───────────┘
│      │
│      └── path length
└───────── GET method code
```

After the path come the two length-prefixed headers.

## Response frame structure

The response begins with another 12-byte fixed header:

```text
42 48 01 02 00 NN 00 00 LL LL LL LL
│  │  │  │  │  │  │  │  └──────── payload length
│  │  │  │  │  │  └──┴────────── reserved
│  │  │  │  │  └──────────────── header count
│  │  │  │  └─────────────────── flags
│  │  │  └────────────────────── frame type = response
│  │  └───────────────────────── version
└──┴──────────────────────────── magic
```

The first two payload bytes are the status:

```text
00 C8
```

which is decimal `200`.

After the headers, all remaining payload bytes are the file body.

## Important observation

The hexdump demonstrates that the wire contains binary fields rather than a
textual HTTP request such as:

```text
GET /index.html HTTP/1.1
```

The protocol can still represent HTTP-like concepts such as a method, path,
status, headers, and body while using a binary frame format.
