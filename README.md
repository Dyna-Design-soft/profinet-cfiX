# cfix-api

Python API for a Hilscher CIFX PROFINET PCI card, plus a TCP/UDP gateway
so LabVIEW (or any other TCP/UDP client) can drive a PROFINET drive
without needing the Hilscher SDK or a LabVIEW driver toolkit installed.

```
Drive (PROFINET) <-> CIFX PCI card <-> cifX driver (Windows)
                                          |
                                   cfix_api.cifx (ctypes)
                                          |
                                   cfix_api.gateway (TCP :9800 / UDP :9801)
                                          |
                                      LabVIEW
```

## Layout

- `src/cfix_api/cifx/` — ctypes bindings to the Hilscher cifX driver API
  (`xDriverOpen`, `xChannelOpen`, `xChannelIORead/Write`,
  `xChannelHostState`, `xChannelBusState`, `xChannelWatchdog`,
  `xChannelReset`), plus a `CifXBackend` abstraction with a real
  (`HilscherCifXBackend`) and mock (`MockCifXBackend`) implementation.
- `src/cfix_api/gateway/` — the TCP/UDP gateway: wire protocol codec
  (`protocol.py`), request dispatch (`dispatch.py`), transports
  (`tcp_server.py`, `udp_server.py`), a bounded live request/response
  recorder for the GUI's Diagnostics window (`traffic_log.py`), config
  (`config.py`) and CLI (`cli.py`).
- `src/cfix_api/gui/` — an optional PySide6 desktop app
  (`cfix-gateway-gui`) that runs the same `GatewayRunner` in-process and
  auto-starts it on launch; a "Gateway Configuration" dialog (TCP/UDP)
  and a "DLL Configuration" dialog (board/channel/driver DLL/mock) are
  the only two settings surfaces, each saving to `gui_config.json` and
  restarting the gateway on OK (see "Where settings are stored" below).
  Requires the `gui` extra (`pip install -e ".[gui]"`); everything else
  in this repo works without it.
- `docs/PROTOCOL.md` — the gateway's binary wire protocol.
- `docs/LABVIEW_INTEGRATION.md` — how to build a LabVIEW TCP/UDP client
  against it.
- `examples/python_client_example.py` — a runnable reference client.
- `tests/` — run entirely against `MockCifXBackend`, no CIFX hardware or
  Windows driver required.

## Requirements

- The gateway process (`cfix_api.gateway`) must run on the Windows PC with
  the Hilscher CIFX PROFINET card and its cifX driver installed, so
  `cfix_api.cifx.HilscherCifXBackend` can load the driver DLL. Set the
  `CIFX_DLL_PATH` environment variable if the DLL isn't found under one of
  its usual names (see `src/cfix_api/cifx/bindings.py`).
- LabVIEW (or any TCP/UDP client) can run on the same or a different
  machine, and talks to the gateway over the network — no cifX driver or
  SDK needed on that side.
- Python 3.9+ for the gateway process itself.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt                 # third-party deps: PySide6 (GUI) + pytest (tests)
pip install -e .                                # this package itself (cfix_api, console scripts)
pytest                                          # runs against the mock backend

# Try the gateway without hardware:
python -m cfix_api.gateway.cli --config config/gateway.mock.json &
python examples/python_client_example.py --transport tcp --port 9800

# Against a real CIFX card, edit config/gateway.example.json
# (board_name, channel, dll_path if needed) then:
python -m cfix_api.gateway.cli --config config/gateway.example.json
```

## Desktop GUI

```bash
pip install -e ".[gui]"
python -m cfix_api.gui.app       # or the `cfix-gateway-gui` console script
```

To build a standalone Windows `.exe` instead of running from source, see
`packaging/README.md`.

The gateway starts automatically the moment the app opens — there's no
Start button. It uses whatever was last saved (defaults to the mock
backend on first run, so it comes up working with no hardware attached),
persisted independent of the CLI's `config/*.json` files (see "Where
settings are stored" below). The window itself is just:

- **Status** — Running/Stopped, bus/host state, TCP client count, live.
- **Gateway Configuration…** — TCP/UDP enabled/host/port, plus a
  Streaming mode section (`stream.enabled` and its area/offset/length/
  write-framing/poll-interval settings — see "Wire protocol" below).
- **DLL Configuration…** — board name, channel, IO timeout, driver DLL
  path, and the mock-backend toggle.
- **Diagnostics…** — a non-modal window with a live table of recent
  TCP/UDP requests/responses (decoded: command, area/offset/length,
  status, data), a live hex view of the card's current input/output
  process data at a chosen offset, and — when streaming mode is active —
  a live write/read KB/s throughput readout (sampled every 300ms from
  cumulative byte counters, not a per-event log: streaming's poll rate is
  too high for a per-event table to be useful). Safe to leave open while
  the gateway keeps running; survives Restart Gateway / config changes.
- **Restart Gateway** — manual recovery (e.g. after fixing a cable or a
  bad DLL path) without closing the app.
- **Log** — live gateway log output.

Either config dialog saves to disk and restarts the gateway on OK, so
changes take effect immediately.

**Gateway Configuration…**, **DLL Configuration…**, and **Restart
Gateway** are locked behind a **Login** button — disabled until a correct
password is entered, and re-locked every time the app starts (no "remember
me"). **Diagnostics…** is read-only and is never gated. This is a local
fat-finger guard, not real multi-user security — anyone with access to the
machine already has access to the config files. The default password is
`admin`; once logged in, use **Change Password…** to set your own (stored
as a salted hash in `auth.json`, separate from `gui_config.json` — see
below for where).

### Where settings are stored

Both `gui_config.json` (gateway config) and `auth.json` (password hash)
live in a `.cfix_gateway` folder, whose location depends on how the app
is running (`app_dirs.py`):

- **Running the built `.exe`** (see `packaging/`): the folder sits right
  next to the executable - e.g. `dist\.cfix_gateway\` alongside
  `dist\CFIX Gateway.exe`. The binary and its settings travel together;
  copying/backing up the folder containing the `.exe` carries its
  settings with it.
- **Running from source** (`python -m cfix_api.gui.app`): falls back to
  `~/.cfix_gateway/` (your home directory), since there's no single "exe
  location" to anchor to.

## Wire protocol

The gateway passes raw PROFINET cyclic process-data bytes through as-is —
it does not parse drive telegrams. See `docs/PROTOCOL.md` for the exact
frame layout (both transports share the same frame; TCP wraps it with a
start byte, a 4-byte length, and an end byte since it's a stream, UDP
uses one frame per datagram).

There's also an opt-in **streaming mode** (`stream.enabled` in the config)
that drops the framed protocol on TCP entirely in favor of fixed-size raw
byte chunks pushed/pulled with no header at all — see the "Streaming mode"
sections in `docs/PROTOCOL.md` and `docs/LABVIEW_INTEGRATION.md`.

## Latency (target: 20-50ms cyclic round trip)

A cyclic control loop's total latency has three independent pieces —
only the middle one is this repo's to control:

1. **LabVIEW ↔ gateway**, over TCP or UDP.
2. **Gateway ↔ cifX driver**, one `xChannelIORead`/`xChannelIOWrite` call
   per direction, bounded by `cifx.io_timeout_ms` (default lowered to
   **20ms** - this is a call timeout, not the fieldbus cycle time; a call
   that already has fresh data returns near-instantly regardless).
3. **CIFX card ↔ drive**, the actual PROFINET RT cycle. This is
   configured on the card itself via Hilscher's bus configuration tool
   (e.g. SycoN/netDevice) - typically 1-8ms on netX hardware - entirely
   outside this gateway's code.

For (1), TCP is a lock-step small-frame request/response protocol, which
is exactly the pattern Nagle's algorithm (batching small writes) plus
delayed ACK is known to stall by tens of milliseconds - landing right in
the middle of a 20-50ms budget if it triggers. The gateway now sets
`TCP_NODELAY` on every accepted connection to rule that out server-side;
`docs/LABVIEW_INTEGRATION.md` already documents writing the start byte,
length prefix, frame, and end byte as a single concatenated write, which
avoids the split-write pattern that triggers it in the first place. UDP has no such issue at
all, at the cost of being unacknowledged/unordered - prefer it if TCP
still shows jitter you can't explain.

**Measured** (this repo's actual software overhead, loopback, mock
backend - i.e. pieces (1)+(2) here, not (3)): `python
examples/latency_benchmark.py --transport tcp --port 9800 -n 1000` gives
a ~0.2ms median / ~2ms max round trip; UDP ~0.8ms median / ~2.8ms max.
Both are roughly two orders of magnitude under budget over loopback, but
loopback isn't your real network or your real card - run the same
benchmark against your actual deployment (real LabVIEW-side machine,
real CIFX card, `mock: false`) to get a real number instead of trusting
this one.

## Status

The `cifx` ctypes bindings (error codes, `BOARD_INFORMATION` /
`CHANNEL_INFORMATION` struct layout, and the `xChannelHostState` /
`xChannelBusState` calling convention) have been cross-checked against
Hilscher's own "PyCifx" reference demo (distributed from their Global
Support knowledgebase) and corrected to match it where they initially
differed. The one remaining unverified piece is the `xChannelWatchdog`
command numbering (stop/start/trigger), since Hilscher's demo doesn't
exercise that call — verify it against the driver installed on the
target Windows machine before relying on `watchdog_trigger()` in
production. Everything else has not yet been exercised against a
physical CIFX card in this repository's test environment (there is no
Windows machine or card here) — do that verification on the target
machine before relying on `HilscherCifXBackend` in production. The
gateway framing, dispatch, and both transports are covered by the test
suite via `MockCifXBackend`.
