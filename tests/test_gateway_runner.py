import pytest

from cfix_api.cifx import errors as e
from cfix_api.gateway.config import CifxConfig, GatewayConfig, TcpConfig, UdpConfig
from cfix_api.gateway.server import GatewayRunner


@pytest.fixture
def runner():
    config = GatewayConfig(
        tcp=TcpConfig(host="127.0.0.1", port=0),
        udp=UdpConfig(enabled=False),
        cifx=CifxConfig(mock=True),
    )
    r = GatewayRunner(config)
    yield r
    r.stop()


def test_start_sets_host_state_ready_automatically(runner):
    """A PROFINET IO controller card won't go active on the bus until the
    host signals ready - previously nothing did this automatically, so the
    card sat configured-but-dormant after every gateway start until
    something else (e.g. SyCon connecting) asserted host-ready as a side
    effect."""
    runner.start()
    _bus_state, host_state = runner.backend.get_status()
    assert host_state == e.CIFX_HOST_STATE_READY


def test_start_still_succeeds_if_set_host_state_fails(runner, monkeypatch):
    def _boom(ready):
        raise e.CifXError("xChannelHostState", e.CIFX_DEV_NOT_READY)

    monkeypatch.setattr(runner.backend, "set_host_state", _boom)

    runner.start()  # must not raise

    assert runner._tcp_server is not None
