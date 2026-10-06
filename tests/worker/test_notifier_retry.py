"""Notifier._post retries transient failures (5xx / connection errors)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from worker import notifier as notifier_mod
from worker.notifier import Notifier


def _resp(code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = code
    if code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(str(code))
    return r


def _hook() -> SimpleNamespace:
    return SimpleNamespace(name="h", timeout_seconds=5)


def test_post_retries_5xx_then_succeeds(monkeypatch) -> None:
    calls = [_resp(503), _resp(503), _resp(200)]
    post = MagicMock(side_effect=calls)
    sleep = MagicMock()
    monkeypatch.setattr(notifier_mod.requests, "post", post)
    monkeypatch.setattr(notifier_mod.time, "sleep", sleep)
    metrics = MagicMock()
    Notifier(metrics=metrics, hostname="t")._post(
        _hook(), "https://x.test", json_body={"a": 1}
    )
    assert post.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [0.5, 1.0]
    metrics.record_notification.assert_called_with("h", True)


def test_post_gives_up_after_retries(monkeypatch) -> None:
    post = MagicMock(return_value=_resp(503))
    monkeypatch.setattr(notifier_mod.requests, "post", post)
    monkeypatch.setattr(notifier_mod.time, "sleep", MagicMock())
    with pytest.raises(requests.HTTPError):
        Notifier(metrics=MagicMock(), hostname="t")._post(
            _hook(), "https://x.test", json_body={}
        )
    assert post.call_count == 3
