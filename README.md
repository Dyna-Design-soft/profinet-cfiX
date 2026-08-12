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
  (`tcp_server.py`, `udp_server.py`), config (`config.py`) and CLI
  (`cli.py`).
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
pip install -e ".[dev]"
pytest                                          # runs against the mock backend

# Try the gateway without hardware:
python -m cfix_api.gateway.cli --config config/gateway.mock.json &
python examples/python_client_example.py --transport tcp --port 9800

# Against a real CIFX card, edit config/gateway.example.json
# (board_name, channel, dll_path if needed) then:
python -m cfix_api.gateway.cli --config config/gateway.example.json
```

## Wire protocol

The gateway passes raw PROFINET cyclic process-data bytes through as-is —
it does not parse drive telegrams. See `docs/PROTOCOL.md` for the exact
frame layout (both transports share the same frame; TCP adds a 4-byte
length prefix since it's a stream, UDP uses one frame per datagram).

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
