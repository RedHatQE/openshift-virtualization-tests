"""Unit tests for utilities.debug remote debugger helpers.

Test structure adapted from the debugging helpers ported from
RedHatQE/mtv-api-tests PR #733 (by myakove — source:
https://github.com/RedHatQE/mtv-api-tests/blob/main/utilities/debug.py).
"""

import bdb
import socket
import sys

import pytest

import utilities.debug
from utilities.debug import (
    _DEFAULT_REMOTE_DEBUGGER_HOST,
    _DEFAULT_REMOTE_DEBUGGER_PORT,
    remote_breakpoint,
    remote_debugger_enabled,
    remote_post_mortem,
)


class _FakeRemotePdb:
    """RemotePdb stand-in recording constructor arguments and interaction state."""

    last_instance: _FakeRemotePdb | None = None

    def __init__(self, host: str, port: int, patch_stdstreams: bool = False) -> None:
        self.host = host
        self.port = port
        self.patch_stdstreams = patch_stdstreams
        self.reset_called = False
        self.interaction_frame = None
        self.interaction_traceback = None
        self.quitting = False
        self.set_trace_frame = None
        _FakeRemotePdb.last_instance = self

    def reset(self) -> None:
        self.reset_called = True

    def interaction(self, frame=None, tb_or_exc=None, **legacy_kwargs) -> None:
        # Signature mirrors Python 3.14 pdb.Pdb.interaction (tb_or_exc) and also accepts the
        # legacy Python <= 3.13 name (traceback) so the version-adaptive call is covered.
        self.interaction_frame = frame
        self.interaction_traceback = tb_or_exc if tb_or_exc is not None else legacy_kwargs.get("traceback")
        self.interaction_arg_names = tuple(
            sorted(name for name in ({"tb_or_exc" if tb_or_exc is not None else None, *legacy_kwargs}) if name)
        )

    def set_trace(self, frame=None) -> None:
        self.set_trace_frame = frame


@pytest.fixture(autouse=True)
def fake_remote_pdb(monkeypatch: pytest.MonkeyPatch):
    """Replace RemotePdb so no real socket listener is opened by any test."""
    monkeypatch.setattr(utilities.debug, "RemotePdb", _FakeRemotePdb)
    _FakeRemotePdb.last_instance = None


def _fake_addrinfos(addresses: list[str]):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in addresses]


def _captured_exception() -> ValueError:
    try:
        raise ValueError("boom")
    except ValueError as err:
        return err


class TestRemoteDebuggerEnabled:
    def test_enabled_when_env_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        assert remote_debugger_enabled() is True, "CNV_REMOTE_PDB set must enable the debugger"

    def test_disabled_when_env_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CNV_REMOTE_PDB", raising=False)
        assert remote_debugger_enabled() is False, "CNV_REMOTE_PDB unset must disable the debugger"


class TestNoOpWhenDisabled:
    def test_breakpoint_returns_without_listener(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CNV_REMOTE_PDB", raising=False)
        remote_breakpoint()
        assert _FakeRemotePdb.last_instance is None, "Disabled breakpoint must not open a listener"

    def test_post_mortem_returns_without_listener(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CNV_REMOTE_PDB", raising=False)
        remote_post_mortem(exception=_captured_exception())
        assert _FakeRemotePdb.last_instance is None, "Disabled post-mortem must not open a listener"


class TestRemoteDebuggerConstruction:
    def test_default_host_and_port(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CNV_REMOTE_PDB", raising=False)
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        debugger = utilities.debug._remote_debugger()
        assert debugger.host == _DEFAULT_REMOTE_DEBUGGER_HOST, "Default host must be loopback"
        assert debugger.port == _DEFAULT_REMOTE_DEBUGGER_PORT, "Default port must be used"

    def test_port_override_plus_xdist_worker_offset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.setenv("REMOTE_PDB_PORT", "5000")
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
        debugger = utilities.debug._remote_debugger()
        assert debugger.port == 5003, "Worker gw3 must listen on base port + 3"

    def test_worker_without_numeric_index_gets_no_offset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "master")
        debugger = utilities.debug._remote_debugger()
        assert debugger.port == _DEFAULT_REMOTE_DEBUGGER_PORT, "Non-gwN worker names must not offset the port"

    def test_numeric_loopback_host_resolves(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.setenv("REMOTE_PDB_HOST", "127.0.0.1")
        debugger = utilities.debug._remote_debugger()
        assert debugger.host == "127.0.0.1", "Numeric loopback host must be used as-is"

    def test_localhost_resolves_to_loopback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.setenv("REMOTE_PDB_HOST", "localhost")
        debugger = utilities.debug._remote_debugger()
        assert debugger.host == "127.0.0.1", "localhost must resolve to the numeric loopback address"

    def test_empty_host_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REMOTE_PDB_HOST", "")
        with pytest.raises(ValueError, match="REMOTE_PDB_HOST must not be empty"):
            utilities.debug._remote_debugger()

    def test_non_loopback_host_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.setattr(
            target=utilities.debug.socket,
            name="getaddrinfo",
            value=lambda host, port, family: _fake_addrinfos(addresses=["192.0.2.10"]),
        )
        monkeypatch.setenv("REMOTE_PDB_HOST", "example.invalid")
        with pytest.raises(ValueError, match="must resolve to a loopback address"):
            utilities.debug._remote_debugger()

    def test_unresolvable_host_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

        def raise_gaierror(host, port, family):
            raise socket.gaierror("no such host")

        monkeypatch.setattr(target=utilities.debug.socket, name="getaddrinfo", value=raise_gaierror)
        monkeypatch.setenv("REMOTE_PDB_HOST", "example.invalid")
        with pytest.raises(ValueError, match="does not resolve"):
            utilities.debug._remote_debugger()

    def test_non_integer_port_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.setenv("REMOTE_PDB_PORT", "http")
        with pytest.raises(ValueError, match="REMOTE_PDB_PORT must be an integer"):
            utilities.debug._remote_debugger()


class TestRemoteBreakpoint:
    def test_set_trace_receives_caller_frame(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        remote_breakpoint()
        debugger = _FakeRemotePdb.last_instance
        assert debugger is not None, "Enabled breakpoint must open a listener"
        assert debugger.set_trace_frame is not None, "set_trace must receive a frame"
        assert debugger.set_trace_frame.f_code is TestRemoteBreakpoint.test_set_trace_receives_caller_frame.__code__, (
            "set_trace must receive the breakpoint caller's frame"
        )

    def test_connection_lost_raises_bdbquit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

        class _DisconnectingPdb(_FakeRemotePdb):
            def set_trace(self, frame=None) -> None:
                raise ConnectionResetError("connection reset by peer")

        monkeypatch.setattr(utilities.debug, "RemotePdb", _DisconnectingPdb)
        with pytest.raises(bdb.BdbQuit, match="connection lost"):
            remote_breakpoint()

    def test_unresolvable_caller_frame_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.setattr(utilities.debug.inspect, "currentframe", lambda: None)
        with pytest.raises(RuntimeError, match="Could not resolve the caller frame"):
            remote_breakpoint()


class TestRemotePostMortem:
    def test_interaction_receives_exception_traceback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        exception = _captured_exception()
        remote_post_mortem(exception=exception)
        debugger = _FakeRemotePdb.last_instance
        assert debugger is not None, "Enabled post-mortem must open a listener"
        assert debugger.reset_called is True, "Post-mortem must reset the debugger before interaction"
        assert debugger.interaction_traceback is exception.__traceback__, (
            "interaction must receive the exception's traceback"
        )
        assert debugger.interaction_arg_names == ("tb_or_exc",), "Python 3.14+ must use the tb_or_exc keyword"

    def test_interaction_uses_legacy_keyword_on_older_python(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "version_info", (3, 12, 0))
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        remote_post_mortem(exception=_captured_exception())
        debugger = _FakeRemotePdb.last_instance
        assert debugger is not None, "Enabled post-mortem must open a listener"
        assert debugger.interaction_traceback is not None, "Legacy keyword must carry the traceback"
        assert debugger.interaction_arg_names == ("traceback",), "Python < 3.14 must use the legacy traceback keyword"

    def test_quitting_raises_bdbquit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

        class _QuittingPdb(_FakeRemotePdb):
            def __init__(self, host: str, port: int, patch_stdstreams: bool = False) -> None:
                super().__init__(host=host, port=port, patch_stdstreams=patch_stdstreams)
                self.quitting = True

        monkeypatch.setattr(utilities.debug, "RemotePdb", _QuittingPdb)
        with pytest.raises(bdb.BdbQuit, match="was quit or disconnected"):
            remote_post_mortem(exception=_captured_exception())

    def test_connection_lost_raises_bdbquit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CNV_REMOTE_PDB", "1")
        monkeypatch.delenv("REMOTE_PDB_HOST", raising=False)
        monkeypatch.delenv("REMOTE_PDB_PORT", raising=False)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

        class _DisconnectingPdb(_FakeRemotePdb):
            def interaction(self, frame=None, tb_or_exc=None, **legacy_kwargs) -> None:
                raise BrokenPipeError("broken pipe")

        monkeypatch.setattr(utilities.debug, "RemotePdb", _DisconnectingPdb)
        with pytest.raises(bdb.BdbQuit, match="connection lost"):
            remote_post_mortem(exception=_captured_exception())
