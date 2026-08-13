# CFIX Gateway Wire Protocol

The gateway relays raw PROFINET cyclic process-data bytes between the
Hilscher CIFX card (via the cifX driver) and a LabVIEW client over TCP or
UDP. It does **not** interpret the process-data contents — LabVIEW is
responsible for packing/unpacking whatever telegram (e.g. PROFIdrive) the
drive uses. All multi-byte integers are **big-endian** ("network" byte
order), which matches LabVIEW's default flatten-to-string / Unflatten From
String byte order.

## Frame layout

Every request and response is a single **frame**:

### Request

| Offset | Size | Field   | Notes                                          |
|-------:|-----:|---------|-------------------------------------------------|
| 0      | 1    | Command | see Commands below                              |
| 1      | 1    | Area    | cifX IO area number (use `0` unless told otherwise) |
| 2      | 2    | Offset  | u16, byte offset into the IO area                |
| 4      | 2    | Length  | u16, byte length of `Data` (request) or requested read length |
| 6      | N    | Data    | present only for `WRITE_OUTPUT`; `N == Length`   |

### Response

| Offset | Size | Field   | Notes                                          |
|-------:|-----:|---------|-------------------------------------------------|
| 0      | 1    | Status  | `0x00` = OK, non-zero = error (see Status codes) |
| 1      | 1    | Command | echoes the request command                      |
| 2      | 2    | Length  | u16, byte length of `Data` that follows          |
| 4      | N    | Data    | present for successful reads / status queries    |

## Commands

| Value  | Name             | Request fields used            | Response data                      |
|-------:|------------------|---------------------------------|-------------------------------------|
| `0x01` | READ_INPUT       | Area, Offset, Length             | `Length` bytes read from the input image  |
| `0x02` | WRITE_OUTPUT     | Area, Offset, Length, Data        | none                                |
| `0x03` | READ_OUTPUT      | Area, Offset, Length             | `Length` bytes read back from the output image |
| `0x10` | GET_STATUS       | none                              | 2 bytes: `[bus_state, host_state]`  |
| `0x11` | SET_HOST_STATE   | Data = 1 byte (0 or 1)            | none                                |
| `0x12` | WATCHDOG_TRIGGER | none                              | none                                |
| `0x13` | RESET            | none                              | none                                |

`READ_INPUT` reads the card's PROFINET **input** process-data image (data
coming *from* the drive). `WRITE_OUTPUT`/`READ_OUTPUT` write/read the
**output** image (data going *to* the drive). This mirrors `xChannelIORead`
/ `xChannelIOWrite`'s area convention on the cifX driver.

## Status codes

| Value  | Meaning                                            |
|-------:|-----------------------------------------------------|
| `0x00` | OK                                                  |
| `0x01` | Malformed frame (too short / bad length)            |
| `0x02` | Unknown command                                     |
| `0x03` | Backend error (cifX driver call failed; see gateway log for the underlying cifX error code) |

## Transport framing

- **TCP**: the connection is a byte stream, so each frame above is
  wrapped as `[START byte][u32 length][frame][END byte]`:
  - `START` = `0x82`, a fixed sync byte.
  - `length` (4 bytes, big-endian) counts only the bytes of `frame` that
    follows — not the START byte, the length field itself, or the END
    byte.
  - `END` = `0x83`, a fixed sync byte, immediately after the `length`
    bytes of frame data.
  - The `length` field is authoritative for how many frame bytes to
    read — the receiver never scans the stream for START/END. It reads
    1 byte (START), 4 bytes (length), `length` bytes (frame), then 1
    more byte (END) and checks it. This means arbitrary binary payload
    bytes (including bytes that happen to equal `0x82`/`0x83`) never get
    misread as a delimiter.
  - A client sends `[0x82][u32 length][frame][0x83]` and reads the
    response the same way. If START or END don't match at their fixed
    offset, the gateway logs a warning and closes the connection — the
    stream is desynced and cannot be recovered without reconnecting.
  - Multiple requests may be pipelined on one connection; each is
    answered in order.
- **UDP**: each datagram *is* one frame, with no start/length/end
  wrapper — the UDP datagram boundary provides the framing. One request
  datagram gets exactly one response datagram from the same server
  socket. UDP is unordered/unreliable, so a client should apply its own
  timeout/retry if a response doesn't arrive.

## Example: read 16 bytes of drive input data at offset 0 (TCP)

Request frame: `01 00 00 00 00 10` (6 bytes)
Sent on the wire as: `82 00 00 00 06 01 00 00 00 00 10 83`
(START + 4-byte length + frame + END)

Response frame (success, 16 bytes of data):
`00 01 00 10 <16 bytes>` (4 + 16 = 20 bytes)
Sent on the wire as: `82 00 00 00 14 00 01 00 10 <16 bytes> 83`

## Streaming mode (`stream.enabled` in the gateway config)

This is a different mode entirely from everything above — no Command byte,
no frame markers, no request/response. It's opt-in via `config.stream` (see
`config/gateway.example.json`, `config/gateway.mock.stream.json`) and, when
on, replaces the framed protocol on the TCP port described above (UDP is
unaffected).

Per TCP connection, two independent loops run at once:

- **Write direction**: the gateway blocks reading exactly `write_length`
  raw bytes from the client (no header, no length prefix — just that many
  bytes), then calls `io_write(area, write_offset, data)` — straight to the
  cifX output image. It then waits for the next `write_length` bytes and
  repeats. There is no response to a write; the client just keeps sending
  fixed-size chunks whenever it has a new value to send.
- **Read direction**: independently of anything the client sends, every
  `poll_interval_ms` the gateway calls `io_read(area, read_offset,
  read_length)` and sends those raw bytes straight to the client — again,
  no header, no length prefix. This isn't a reply to a request; it's a
  continuous, unprompted push at a fixed rate for as long as the connection
  is open.

Because the two directions are independent loops, the client can write and
read as separate LabVIEW loops too — one loop doing `TCP Write` of
`write_length` bytes whenever it has a new setpoint, another loop doing
`TCP Read` of `read_length` bytes in an unconditional loop to drain the
continuous stream of status data. There's nothing to correlate a read with
a write; the input data you get back is just "whatever the drive's input
image held at the last poll," not a response to any particular write.

`write_length`/`read_length` are fixed per gateway config — every chunk in
each direction is exactly that many bytes, so no length field is needed on
the wire to know where one chunk ends and the next begins.
