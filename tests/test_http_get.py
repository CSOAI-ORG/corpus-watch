"""Offline tests for spine.adapters.http_get failure handling. The guard exists because the
daily run reported two gesetze-im-internet.de documents UNREACHABLE as a bare
'<urlopen error timed out>' after 4 x 90 s, while the same URLs answer from elsewhere with the
frozen bytes: the report must say which phase failed, and a dropped path must not cost the
full retry budget twice in one pass."""
import socket
import urllib.error

import pytest

from spine import adapters as A
from spine import engine as E


class _Resp:
    def __init__(self, body=b"ok", url="https://example.test/x"):
        self.body, self.url, self.headers = body, url, {}

    def geturl(self):
        return self.url

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    A.reset_host_state()
    sleeps = []
    monkeypatch.setattr(A.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(A.urllib.request, "getproxies", lambda: {})
    yield sleeps
    A.reset_host_state()


def _timeout_urlopen(calls):
    def f(req, timeout=None):
        calls.append(req.full_url)
        raise urllib.error.URLError(socket.timeout("timed out"))
    return f


def test_backoff_is_bounded_exponential(_clean):
    assert [A._backoff(i) for i in range(5)] == [5, 15, 45, 60, 60]


def test_connect_timeout_is_named_and_host_is_skipped_for_the_pass(monkeypatch, _clean):
    calls = []
    monkeypatch.setattr(A.urllib.request, "urlopen", _timeout_urlopen(calls))
    def no_route(addr, timeout=None):
        raise socket.timeout("timed out")
    monkeypatch.setattr(A.socket, "create_connection", no_route)
    with pytest.raises(A.Unreachable) as e1:
        A.http_get("https://www.gesetze-im-internet.de/bdsg_2018/xml.zip", timeout=1, tries=4)
    msg = str(e1.value)
    assert msg.startswith("URLError: <urlopen error timed out>")
    assert "phase=connect-timeout" in msg and "host=www.gesetze-im-internet.de" in msg and "tries=4" in msg
    assert len(calls) == 4
    assert _clean == [5, 15, 45]          # no sleep after the last try
    with pytest.raises(A.Unreachable) as e2:
        A.http_get("https://www.gesetze-im-internet.de/ki-mig/xml.zip", timeout=1, tries=4)
    assert len(calls) == 4                 # skipped: no new request to a host whose TCP path is down
    assert "skipped" in str(e2.value) and "phase=connect-timeout" in str(e2.value)


def test_slow_server_is_response_timeout_and_never_skipped(monkeypatch, _clean):
    calls = []
    monkeypatch.setattr(A.urllib.request, "urlopen", _timeout_urlopen(calls))
    class _Sock:
        def close(self):
            pass
    monkeypatch.setattr(A.socket, "create_connection", lambda addr, timeout=None: _Sock())
    for path in ("a", "b"):
        with pytest.raises(A.Unreachable) as e:
            A.http_get(f"https://slow.example.test/{path}", timeout=1, tries=2)
        assert "phase=response-timeout" in str(e.value)
    assert len(calls) == 4                 # both URLs tried in full
    assert A._HOST_DOWN == {}


def test_behind_a_proxy_no_probe_and_no_skip(monkeypatch, _clean):
    calls = []
    monkeypatch.setattr(A.urllib.request, "urlopen", _timeout_urlopen(calls))
    monkeypatch.setattr(A.urllib.request, "getproxies", lambda: {"https": "http://proxy:3128"})
    def must_not_probe(*a, **k):
        raise AssertionError("direct TCP probe behind a proxy")
    monkeypatch.setattr(A.socket, "create_connection", must_not_probe)
    with pytest.raises(A.Unreachable) as e:
        A.http_get("https://www.gesetze-im-internet.de/x", timeout=1, tries=2)
    assert "phase=open-timeout" in str(e.value) and A._HOST_DOWN == {}


def test_transient_timeout_then_success_returns_bytes(monkeypatch, _clean):
    seq = [urllib.error.URLError(socket.timeout("timed out")), _Resp(b"PK-bytes")]
    def f(req, timeout=None):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(A.urllib.request, "urlopen", f)
    body, _ = A.http_get("https://www.gesetze-im-internet.de/bdsg_2018/xml.zip", timeout=1, tries=4)
    assert body == b"PK-bytes" and _clean == [5]


def test_read_timeout_and_dns_phases(monkeypatch, _clean):
    class _SlowBody(_Resp):
        def read(self):
            raise socket.timeout("timed out")
    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=None: _SlowBody())
    with pytest.raises(A.Unreachable) as e:
        A.http_get("https://a.example.test/x", timeout=1, tries=1)
    assert "phase=read-timeout" in str(e.value)
    def dns(req, timeout=None):
        raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
    monkeypatch.setattr(A.urllib.request, "urlopen", dns)
    with pytest.raises(A.Unreachable) as e:
        A.http_get("https://b.example.test/x", timeout=1, tries=1)
    assert "phase=dns" in str(e.value)


def test_authority_403_is_still_blocked_not_unreachable(monkeypatch, _clean):
    calls = []
    def forbidden(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(A.urllib.request, "urlopen", forbidden)
    with pytest.raises(A.Unreachable) as e:
        A.http_get("https://ndpc.gov.ng/x.pdf", timeout=1, tries=4)
    assert len(calls) == 1 and "phase=http-403" in str(e.value)
    doc = {"adapter": "pinned_document", "instrument_id": "NG-x", "url": "https://ndpc.gov.ng/x.pdf",
           "celex": None, "jurisdiction": "NG", "frozen_document_sha256": None,
           "rows": [{"provision_id": "NG-x:1"}]}
    def fetch(a, u, c):
        raise e.value
    res = E.measure_doc(doc, gate=True, fetch=fetch)
    assert res["doc"]["gate"] == "BLOCKED"


def test_connect_timeout_is_unreachable_not_blocked(monkeypatch, _clean):
    monkeypatch.setattr(A.urllib.request, "urlopen", _timeout_urlopen([]))
    def no_route(addr, timeout=None):
        raise socket.timeout("timed out")
    monkeypatch.setattr(A.socket, "create_connection", no_route)
    with pytest.raises(A.Unreachable) as e:
        A.http_get("https://www.gesetze-im-internet.de/ki-mig/xml.zip", timeout=1, tries=1)
    doc = {"adapter": "pinned_document", "instrument_id": "DE-ki-mig-2026", "url": "https://www.gesetze-im-internet.de/ki-mig/xml.zip",
           "celex": None, "jurisdiction": "DE", "frozen_document_sha256": None,
           "rows": [{"provision_id": "DE-ki-mig-2026:1"}]}
    def fetch(a, u, c):
        raise e.value
    res = E.measure_doc(doc, gate=True, fetch=fetch)
    assert res["doc"]["gate"] == "UNREACHABLE"
    assert res["provisions"]["DE-ki-mig-2026:1"]["class"] == "UNKNOWN"
