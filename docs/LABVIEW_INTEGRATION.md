# LabVIEW Integration Guide

The gateway (`cfix_api.gateway`) runs on the Windows PC with the Hilscher
CIFX PROFINET card installed, and speaks the frame protocol in
`docs/PROTOCOL.md` over TCP and/or UDP. LabVIEW is a plain client: no
Hilscher SDK, DLL, or LabVIEW driver toolkit is required on the LabVIEW
side — only standard LabVIEW TCP/UDP VIs.

All integers in the protocol are **big-endian**, which is LabVIEW's
default byte order for Flatten To String / Unflatten From String and for
Type Cast, so no byte-swapping is needed if you build frames with those
primitives.

There are two TCP modes: the **framed request/response protocol** below
(Command byte, length prefix, explicit reply per request), and a simpler
**streaming mode** with no frame protocol at all — just fixed-size raw
byte chunks in each direction, described further down. Streaming mode is
opt-in via the gateway config (`stream.enabled`) and is what to use if you
don't want to build/parse any header in LabVIEW.

## Streaming mode (`stream.enabled` — no Command byte, no framing)

Turn this on in the gateway's config file (see
`config/gateway.mock.stream.json` for a working example):

```json
"stream": {
  "enabled": true,
  "area": 0,
  "write_offset": 0,
  "write_length": 4,
  "read_offset": 0,
  "read_length": 4,
  "poll_interval_ms": 10
}
```

With this on, the TCP port (`9800` by default) stops speaking the framed
protocol below entirely. Instead:

- **Write loop (LabVIEW → gateway → drive)**: build a byte array of
  exactly `write_length` bytes (your setpoint/control word) and **TCP
  Write** it — nothing else, no header, no length, no command. Whenever
  the gateway has received `write_length` bytes, it writes them straight
  to the cifX output image at (`area`, `write_offset`). Run this in a
  Timed Loop at whatever rate you want to send new setpoints.
- **Read loop (gateway → LabVIEW)**: in a separate loop (or the same one,
  after the write), **TCP Read** exactly `read_length` bytes — again no
  header to strip. The gateway pushes a fresh chunk from the cifX input
  image at (`area`, `read_offset`) every `poll_interval_ms`, unprompted —
  it is **not** a reply to your write, it's a continuous feed. If your
  read loop runs slower than `poll_interval_ms`, TCP just buffers the
  backlog; read in multiples of `read_length` bytes if you want to drain
  it and keep only the latest.
- These two loops are independent — you can structure them as two
  parallel LabVIEW loops on the same TCP Read/Write refnum, one only ever
  writing, one only ever reading.
- `write_length` and `read_length` are config-side constants — every
  chunk in each direction is always exactly that many bytes, which is how
  the gateway knows where one chunk ends without a length field on the
  wire.

Verify it without LabVIEW first:

```bash
python -m cfix_api.gateway.cli --config config/gateway.mock.stream.json
```

then connect with any raw TCP tool (e.g. `nc 127.0.0.1 9800`, or a short
Python script using plain `socket.sendall`/`socket.recv`) and confirm 4
bytes come back every ~10ms, and that whatever 4 bytes you send show up on
the next read.

## Framed protocol — TCP client (VI outline)

1. **TCP Open Connection** to the gateway host/port (default `9800`).
2. Build the request frame as a byte string:
   - `Command` (U8) — e.g. `1` for `READ_INPUT`
   - `Area` (U8) — `0` unless configured otherwise
   - `Offset` (U16, big-endian)
   - `Length` (U16, big-endian)
   - `Data` (only for `WRITE_OUTPUT`, `Length` bytes)
   - Easiest built with **Flatten To String** on a cluster of
     `U8, U8, U16, U16` (+ a byte array for `Data`), with "network byte
     order" left checked (default).
3. Wrap the frame with a fixed **START byte** `0x82`, its length as a
   **U32 big-endian** (4 bytes), and a fixed **END byte** `0x83`, then
   concatenate: `[0x82][length][frame][0x83]`. Build `0x82`/`0x83` as
   plain U8 constants — don't try to detect them elsewhere in the byte
   stream, they're only meaningful at these fixed positions.
4. **TCP Write** the concatenated bytes in one write.
5. **TCP Read** exactly 1 byte and check it's `0x82`, then **TCP Read**
   exactly 4 bytes and **Unflatten From String** as U32 to get the
   response length, then **TCP Read** exactly that many more bytes for
   the response frame, then **TCP Read** exactly 1 more byte and check
   it's `0x83`.
6. **Unflatten From String** the response frame as a cluster of
   `U8 (status), U8 (command), U16 (data length)`, then take the
   remaining bytes as `Data`.
7. Check `status == 0`; non-zero means the gateway rejected the frame or
   the CIFX driver call failed (see `docs/PROTOCOL.md` for status codes).
   Separately, if the START or END byte you read back doesn't match,
   the stream is desynced and the gateway will have already closed the
   connection — don't retry reads on the same connection, reopen it.
8. **TCP Close Connection** when done, or keep it open and repeat steps
   2–7 for each cyclic poll (recommended for a periodic drive-control
   loop — avoid reopening the connection every scan).

## UDP client (VI outline)

1. **UDP Open** a socket (no fixed remote endpoint needed).
2. Build the request frame exactly as in TCP step 2 — **no length
   prefix** for UDP; the datagram itself is the frame.
3. **UDP Write** the frame to the gateway host/port (default `9801`).
4. **UDP Read** up to e.g. 2048 bytes with a timeout (drive loops
   typically want a short timeout, e.g. 50–200 ms, with a retry/skip
   policy on timeout since UDP is not guaranteed to arrive).
5. Parse the response the same way as the TCP case (no length prefix to
   strip).

## Typical cyclic drive loop

For periodic control (e.g. every 10 ms in a Timed Loop):

1. `WRITE_OUTPUT` — send the current control word / setpoint bytes your
   drive telegram expects, at the configured offset.
2. `READ_INPUT` — read back the drive's status word / actual value
   bytes.

The gateway does not interpret these bytes (see PROTOCOL.md) — the
control/status word layout (e.g. a PROFIdrive telegram) is defined by the
drive's PROFINET configuration and must be packed/unpacked on the LabVIEW
side, matching the offsets configured for the drive slot in your PROFINET
engineering tool (e.g. Siemens TIA Portal / PROFINET GSDML config used to
set up the CIFX PROFINET controller).

## Verifying the gateway without LabVIEW or hardware

Run the gateway against the built-in mock backend (no CIFX card needed)
and use the bundled Python client to sanity-check your framing before
wiring up LabVIEW:

```bash
python -m cfix_api.gateway.cli --config config/gateway.mock.json
python examples/python_client_example.py --transport tcp --port 9800
```
