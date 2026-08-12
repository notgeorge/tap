"""Tests for the HTTP serving probes (req-tap-health-probes-7).

These probes exist because every other probe runs *in the calling process* and
stays green while the web worker is dead — the "spawn said done, then I found
the web and api had died" gap. They must therefore be honest about three cases:
serving, not serving, and not-supposed-to-be-serving.
"""

from __future__ import annotations

from unittest import mock

import pytest

from tap_health.probes import probe_http_api, probe_http_web
from tap_health.results import ProbeStatus


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.spec("req-tap-health-probes-7")
@pytest.mark.parametrize("status", [200, 302, 303])
def test_web_serving_statuses_are_healthy(settings, status):
    # A 302 into the login wall is proof of life, not a failure: it means the WSGI
    # stack, middleware chain and login wall all executed. Requiring a 200 would
    # force an unauthenticated surface back into existence (req-tap-health-exposure-4).
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"
    with mock.patch("requests.get", return_value=_Response(status)):
        result = probe_http_web()
    assert result.status is ProbeStatus.HEALTHY
    assert result.context["status"] == status


@pytest.mark.spec("req-tap-health-probes-7")
@pytest.mark.parametrize("status", [200, 401, 403])
def test_api_serving_statuses_are_healthy(settings, status):
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"
    with mock.patch("requests.get", return_value=_Response(status)):
        result = probe_http_api()
    assert result.status is ProbeStatus.HEALTHY


@pytest.mark.spec("req-tap-health-probes-7")
def test_server_error_is_unhealthy(settings):
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"
    with mock.patch("requests.get", return_value=_Response(500)):
        result = probe_http_web()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "http.web.unexpected_status"
    assert result.context["status"] == 500


@pytest.mark.spec("req-tap-health-probes-7")
def test_unreachable_server_is_unhealthy(settings):
    # The case the gate cares about most: the process is up, the server is not.
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"
    with mock.patch("requests.get", side_effect=OSError("connection refused")):
        result = probe_http_api()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "http.api.unreachable"


@pytest.mark.spec("req-tap-health-probes-7")
def test_probe_never_raises_on_a_hang(settings):
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"

    class _Timeout(Exception):
        pass

    with mock.patch("requests.get", side_effect=_Timeout("read timed out")):
        result = probe_http_web()  # must not propagate
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.context["timeout_seconds"] > 0


@pytest.mark.spec("req-tap-health-probes-7")
def test_unset_base_url_is_unknown_not_unhealthy(settings):
    # A process that is not meant to serve must not be reported as broken —
    # `unknown` is visible without being a false alarm (Law 1).
    settings.TAP_HEALTH_SELF_URL = ""
    result = probe_http_web()
    assert result.status is ProbeStatus.UNKNOWN
    assert result.code == "http.web.not_configured"


@pytest.mark.spec("req-tap-health-probes-7")
def test_requests_are_bounded_and_do_not_follow_redirects(settings):
    # allow_redirects=False is load-bearing: following the login redirect would
    # turn the cheap proof-of-life into a rendered page fetch, and would hide a
    # redirect loop. The timeout is what bounds a health run (no runner budget).
    settings.TAP_HEALTH_SELF_URL = "http://127.0.0.1:8000"
    with mock.patch("requests.get", return_value=_Response(302)) as get:
        probe_http_web()
    _, kwargs = get.call_args
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] > 0
