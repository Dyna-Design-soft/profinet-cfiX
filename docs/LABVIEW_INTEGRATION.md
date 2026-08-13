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

## TCP client (VI outline)

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
