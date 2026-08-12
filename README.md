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
- `src/cfix_api/gui/` — an optional PySide6 desktop app
  (`cfix-gateway-gui`) that runs the same `GatewayRunner` in-process and
  auto-starts it on launch; a "Gateway Configuration" dialog (TCP/UDP)
  and a "DLL Configuration" dialog (board/channel/driver DLL/mock) are
  the only two settings surfaces, each saving to
  `~/.cfix_gateway/gui_config.json` and restarting the gateway on OK.
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
pip install -e ".[dev]"
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

The gateway starts automatically the moment the app opens — there's no
Start button. It uses whatever was last saved (defaults to the mock
backend on first run, so it comes up working with no hardware attached),
persisted to `~/.cfix_gateway/gui_config.json` independent of the CLI's
`config/*.json` files. The window itself is just:

- **Status** — Running/Stopped, bus/host state, TCP client count, live.
- **Gateway Configuration…** — TCP/UDP enabled/host/port.
- **DLL Configuration…** — board name, channel, IO timeout, driver DLL
  path, and the mock-backend toggle.
- **Restart Gateway** — manual recovery (e.g. after fixing a cable or a
  bad DLL path) without closing the app.
- **Log** — live gateway log output.

Either config dialog saves to disk and restarts the gateway on OK, so
changes take effect immediately.

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
