import pytest

from tools.backend_spi import BackendError, FakeBackend


def test_fake_backend_is_deterministic_and_semantics_free():
    backend = FakeBackend()
    assert backend.submit("w1", {"issue": 41})["state"] == "submitted"
    assert backend.observe("w1")["state"] == "submitted"
    assert backend.complete("w1", {"ok": True})["state"] == "completed"
    assert backend.observations[0]["event"] == "submitted"
    with pytest.raises(BackendError):
        backend.submit("w1", {})

