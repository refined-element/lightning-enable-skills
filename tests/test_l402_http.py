"""The unpaid probe: vetted addresses, bounded redirects, header hygiene.

HTTP is faked except in the loopback test, which serves one 402 from
127.0.0.1 with --allow-private semantics. Nothing leaves the machine.
"""
import http.server
import socketserver
import ssl
import threading

import pytest

import l402_check_support as support
import l402_http


def resolver(mapping):
    return support.fake_resolver(mapping)


def test_redirect_into_private_range_is_not_followed():
    fixture = support.load_fixture("synthetic-redirect-private")
    log = []
    result = l402_http.probe(
        fixture["request"]["url"], resolver=resolver(fixture["dns"]),
        transport=support.fake_transport(fixture["responses"], log),
    )
    assert result.error_kind == "redirect_refused"
    assert result.error_reason == "private_address"
    assert [entry["url"] for entry in log] == ["https://api.example.com/paid"]


def test_redirects_are_bounded():
    responses = [
        {"url": f"https://api.example.com/r{i}", "status": 302,
         "headers": [["Location", f"/r{i + 1}"]], "body": ""}
        for i in range(10)
    ]
    result = l402_http.probe("https://api.example.com/r0", resolver=resolver({}),
                             transport=support.fake_transport(responses), max_redirects=3)
    assert result.error_kind == "redirect_limit"
    assert len(result.hops) == 4


def test_a_followed_redirect_is_recorded_as_a_hop():
    responses = [
        {"url": "https://api.example.com/old", "status": 301, "headers": [["Location", "/new"]], "body": ""},
        {"url": "https://api.example.com/new", "status": 402, "headers": [], "body": ""},
    ]
    result = l402_http.probe("https://api.example.com/old", resolver=resolver({}),
                             transport=support.fake_transport(responses))
    assert result.error_kind is None
    assert result.response.status == 402
    assert [(h.url, h.status) for h in result.hops] == [("https://api.example.com/old", 301)]
    assert result.final_target.url == "https://api.example.com/new"


def test_https_to_http_downgrade_is_refused():
    responses = [{"url": "https://api.example.com/a", "status": 301,
                  "headers": [["Location", "http://api.example.com/a"]], "body": ""}]
    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}),
                             transport=support.fake_transport(responses))
    assert result.error_kind == "redirect_refused"
    assert result.error_reason == "downgrade"


def test_caller_headers_are_dropped_when_a_redirect_leaves_the_origin():
    # The brief used X-Api-Key here; credential-bearing names are refused
    # outright, so a harmless custom header stands in for it.
    responses = [
        {"url": "https://api.example.com/a", "status": 302, "headers": [["Location", "https://cdn.example.net/a"]], "body": ""},
        {"url": "https://cdn.example.net/a", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    l402_http.probe("https://api.example.com/a", headers={"X-Fixture-Header": "fixture-string-header-value"},
                    resolver=resolver({}), transport=support.fake_transport(responses, log))
    assert log[0]["headers"]["X-Fixture-Header"] == "fixture-string-header-value"
    assert "X-Fixture-Header" not in log[1]["headers"]


def test_timeouts_are_reported_not_raised():
    def slow(target, method, headers, body, timeout):
        raise TimeoutError()

    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}), transport=slow, timeout=2)
    assert result.error_kind == "timeout"
    assert result.response is None


def test_refused_first_hop_never_reaches_the_transport():
    log = []
    result = l402_http.probe("https://10.0.0.1/a", transport=support.fake_transport([], log))
    assert result.error_kind == "refused"
    assert log == []


@pytest.mark.parametrize("name", [
    "Authorization", "authorization", " AUTHORIZATION ", "Cookie", "Proxy-Authorization",
    "X-Api-Key", "apikey", "X-Auth-Token", "Client-Secret", "X-Password", "Session-Id",
    "X-SESSIONID", "X-Auth", "Grpc-Metadata-macaroon", "X-Credential", "X-Preimage",
])
def test_credential_header_names_are_refused_before_any_request(name):
    log = []
    with pytest.raises(l402_http.CredentialHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={name: "fixture-string-header-value"},
                        resolver=resolver({}), transport=support.fake_transport([], log))
    assert log == []
    assert caught.value.header_name == name
    assert "fixture-string-header-value" not in str(caught.value)


@pytest.mark.parametrize("name", [
    "Host", "host", " HOST ", "Content-Length", "Transfer-Encoding", "transfer-encoding", "Connection",
])
def test_host_and_framing_header_names_are_refused_before_any_request(name):
    log = []
    with pytest.raises(l402_http.ReservedHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={name: "fixture-string-header-value"},
                        resolver=resolver({}), transport=support.fake_transport([], log))
    assert log == []
    assert isinstance(caught.value, l402_http.RefusedHeaderError)
    assert caught.value.header_name == name
    assert caught.value.reason == "reserved_header"
    assert "fixture-string-header-value" not in str(caught.value)


@pytest.mark.parametrize("status", [307, 308])
@pytest.mark.parametrize("location", [
    "https://cdn.example.net/a",  # host differs
    "https://api.example.com:8443/a",  # port differs
])
def test_a_body_is_never_resent_across_origins(status, location):
    responses = [{"url": "https://api.example.com/a", "status": status,
                  "headers": [["Location", location]], "body": ""}]
    log = []
    result = l402_http.probe("https://api.example.com/a", method="POST", body=b'{"fixture":"string"}',
                             resolver=resolver({}), transport=support.fake_transport(responses, log))
    assert result.error_kind == "redirect_refused"
    assert result.error_reason == "redirect_cross_origin_with_body"
    assert [(h.url, h.status) for h in result.hops] == [("https://api.example.com/a", status)]
    assert [entry["url"] for entry in log] == ["https://api.example.com/a"]


@pytest.mark.parametrize("status", [307, 308])
def test_a_same_origin_307_or_308_resends_the_body(status):
    responses = [
        {"url": "https://api.example.com/a", "status": status, "headers": [["Location", "/b"]], "body": ""},
        {"url": "https://api.example.com/b", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    result = l402_http.probe("https://api.example.com/a", method="POST", body=b'{"fixture":"string"}',
                             resolver=resolver({}), transport=support.fake_transport(responses, log))
    assert result.error_kind is None
    assert result.response.status == 402
    assert [(entry["method"], entry["body"]) for entry in log] == [
        ("POST", b'{"fixture":"string"}'), ("POST", b'{"fixture":"string"}'),
    ]


def test_a_cross_origin_307_without_a_body_is_followed():
    responses = [
        {"url": "https://api.example.com/a", "status": 307, "headers": [["Location", "https://cdn.example.net/a"]], "body": ""},
        {"url": "https://cdn.example.net/a", "status": 402, "headers": [], "body": ""},
    ]
    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}),
                             transport=support.fake_transport(responses))
    assert result.error_kind is None
    assert result.response.status == 402


def test_a_303_drops_the_body_and_may_change_origin():
    responses = [
        {"url": "https://api.example.com/a", "status": 303, "headers": [["Location", "https://cdn.example.net/a"]], "body": ""},
        {"url": "https://cdn.example.net/a", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    result = l402_http.probe("https://api.example.com/a", method="POST", body=b'{"fixture":"string"}',
                             resolver=resolver({}), transport=support.fake_transport(responses, log))
    assert result.error_kind is None
    assert [(entry["method"], entry["body"]) for entry in log[1:]] == [("GET", None)]


@pytest.mark.parametrize("name", ["Accept", "Content-Type", "X-Request-Id", "Accept-Language", "X-Fixture-Header"])
def test_non_secret_header_names_are_sent(name):
    log = []
    l402_http.probe("https://api.example.com/a", headers={name: "fixture-string-header-value"},
                    resolver=resolver({}), transport=support.fake_transport([], log))
    assert log[0]["headers"][name] == "fixture-string-header-value"


def test_every_hop_is_vetted_and_pinned_to_its_first_address():
    dns = {
        "api.example.com": ["93.184.215.14", "93.184.215.15"],
        "cdn.example.net": ["151.101.1.69", "151.101.65.69"],
    }
    responses = [
        {"url": "https://api.example.com/a", "status": 302, "headers": [["Location", "https://cdn.example.net/a"]], "body": ""},
        {"url": "https://cdn.example.net/a", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    result = l402_http.probe("https://api.example.com/a", resolver=resolver(dns),
                             transport=support.fake_transport(responses, log))
    assert result.error_kind is None
    assert [entry["address"] for entry in log] == ["93.184.215.14", "151.101.1.69"]
    assert [h.address for h in result.hops] == ["93.184.215.14"]
    assert result.connected_address == "151.101.1.69"


def test_a_redirect_host_that_fails_to_resolve_is_reported():
    def flaky(host, port):
        if host == "gone.example.org":
            raise l402_http.ResolutionError("could not resolve host")
        return [support.PUBLIC_TEST_ADDRESS]

    responses = [{"url": "https://api.example.com/a", "status": 302,
                  "headers": [["Location", "https://gone.example.org/a"]], "body": ""}]
    log = []
    result = l402_http.probe("https://api.example.com/a", resolver=flaky,
                             transport=support.fake_transport(responses, log))
    assert result.error_kind == "dns"
    assert len(log) == 1


def test_pinned_transport_connects_to_the_vetted_address_without_resolving(monkeypatch):
    calls = []

    def no_dns(*args, **kwargs):
        raise AssertionError("the transport must not resolve the host name")

    def fake_connect(address, timeout=None, *args, **kwargs):
        calls.append(address)
        raise ConnectionRefusedError()

    monkeypatch.setattr(l402_http.socket, "getaddrinfo", no_dns)
    monkeypatch.setattr(l402_http.socket, "create_connection", fake_connect)
    target = l402_http.Target(url="https://api.example.com/a", scheme="https", host="api.example.com",
                              port=443, path_query="/a", addresses=["93.184.215.14", "93.184.215.15"])
    with pytest.raises(ConnectionRefusedError):
        l402_http.pinned_transport(target, "GET", {"User-Agent": l402_http.USER_AGENT}, None, 2.0)
    assert calls == [("93.184.215.14", 443)]


def test_a_refused_connection_is_a_network_error():
    def refused(target, method, headers, body, timeout):
        raise ConnectionRefusedError()

    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}), transport=refused)
    assert result.error_kind == "network"
    assert result.error_message == "ConnectionRefusedError"


@pytest.mark.parametrize("value", [
    "fixture-string-a\r\nX-Injected: fixture-string-b",
    "fixture-string-a\nfixture-string-b",
    "fixture-string-a\rfixture-string-b",
    b"fixture-string-a\r\nfixture-string-b",
])
def test_header_values_with_cr_or_lf_are_refused_without_echoing_them(value):
    log = []
    with pytest.raises(l402_http.RefusedHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={"X-Fixture-Header": value},
                        resolver=resolver({}), transport=support.fake_transport([], log))
    assert log == []
    assert caught.value.reason == "invalid_header_value"
    assert caught.value.header_name == "X-Fixture-Header"
    assert "fixture-string" not in str(caught.value)


def test_header_values_outside_latin_1_are_refused_without_echoing_them():
    log = []
    with pytest.raises(l402_http.RefusedHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={"X-Fixture-Header": "fixture-string-☃"},
                        resolver=resolver({}), transport=support.fake_transport([], log))
    assert log == []
    assert caught.value.reason == "invalid_header_value"
    assert "fixture-string" not in str(caught.value)
    assert "☃" not in str(caught.value)


def test_latin_1_header_values_are_sent():
    log = []
    l402_http.probe("https://api.example.com/a", headers={"Accept-Language": "fixture-string-café"},
                    resolver=resolver({}), transport=support.fake_transport([], log))
    assert log[0]["headers"]["Accept-Language"] == "fixture-string-café"


def test_header_names_that_are_not_http_tokens_are_refused():
    with pytest.raises(l402_http.RefusedHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={"X-Fixture Header": "fixture-string-value"},
                        resolver=resolver({}), transport=support.fake_transport([]))
    assert caught.value.reason == "invalid_header_name"
    assert "fixture-string-value" not in str(caught.value)


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


def test_each_hop_gets_only_the_time_remaining(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(l402_http, "_clock", clock)
    budgets = []

    def send(target, method, headers, body, timeout):
        budgets.append(timeout)
        clock.now += 6
        if target.url.endswith("/a"):
            return l402_http.HttpResponse(status=302, headers=[("Location", "/b")])
        return l402_http.HttpResponse(status=402, headers=[])

    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}), transport=send, timeout=10)
    assert budgets[0] == 10
    assert len(budgets) == 2 and budgets[1] == pytest.approx(4)
    assert result.error_kind is None


def test_the_deadline_covers_the_whole_probe(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(l402_http, "_clock", clock)
    calls = []

    def send(target, method, headers, body, timeout):
        calls.append(target.url)
        clock.now += 11
        return l402_http.HttpResponse(status=302, headers=[("Location", "/b")])

    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}), transport=send, timeout=10)
    assert result.error_kind == "timeout"
    assert result.error_message == "no response within 10 s"
    assert calls == ["https://api.example.com/a"]


def test_a_network_error_after_the_deadline_is_a_timeout(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(l402_http, "_clock", clock)

    def send(target, method, headers, body, timeout):
        clock.now += 11
        raise ConnectionResetError()

    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}), transport=send, timeout=10)
    assert result.error_kind == "timeout"


def test_the_deadline_helper(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(l402_http, "_clock", clock)
    deadline = l402_http._Deadline(5)
    clock.now += 2
    assert deadline.remaining() == pytest.approx(3)
    assert not deadline.expired()
    clock.now += 3
    assert deadline.expired()
    with pytest.raises(TimeoutError, match="no response within 5 s"):
        deadline.remaining()


def test_a_protocol_relative_location_keeps_the_scheme():
    responses = [
        {"url": "https://api.example.com/a", "status": 302, "headers": [["Location", "//cdn.example.net/x"]], "body": ""},
        {"url": "https://cdn.example.net/x", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}),
                             transport=support.fake_transport(responses, log))
    assert result.error_kind is None
    assert [entry["url"] for entry in log] == ["https://api.example.com/a", "https://cdn.example.net/x"]


def test_a_3xx_without_location_is_returned_not_followed():
    responses = [{"url": "https://api.example.com/a", "status": 302, "headers": [], "body": ""}]
    log = []
    result = l402_http.probe("https://api.example.com/a", resolver=resolver({}),
                             transport=support.fake_transport(responses, log))
    assert result.error_kind is None
    assert result.response.status == 302
    assert result.hops == []
    assert len(log) == 1


@pytest.mark.parametrize("status", [301, 302, 303])
def test_a_head_redirect_keeps_head_and_drops_the_body(status):
    responses = [
        {"url": "https://api.example.com/a", "status": status, "headers": [["Location", "/b"]], "body": ""},
        {"url": "https://api.example.com/b", "status": 402, "headers": [], "body": ""},
    ]
    log = []
    l402_http.probe("https://api.example.com/a", method="HEAD", body=b"fixture-string-body",
                    resolver=resolver({}), transport=support.fake_transport(responses, log))
    assert [(entry["method"], entry["body"]) for entry in log] == [
        ("HEAD", b"fixture-string-body"), ("HEAD", None),
    ]


class _FakeSock:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)


class _FakeResponse:
    def __init__(self, status, headers, body, on_read=None):
        self.status = status
        self._headers = headers
        self._body = body
        self._on_read = on_read
        self.read_sizes = []
        self.closed = False

    def getheaders(self):
        return list(self._headers)

    def isclosed(self):
        return self.closed

    def read(self, *args):
        raise AssertionError("read() is never used; the body is read in chunks with read1")

    def read1(self, n):
        self.read_sizes.append(n)
        if self._on_read:
            self._on_read()
        chunk, self._body = self._body[:n], self._body[n:]
        return chunk

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, response):
        self.response = response
        self.sock = None
        self.timeout = None
        self.requests = []
        self.closed = False

    def connect(self):
        self.sock = _FakeSock()

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def _target(scheme="https"):
    return l402_http.Target(url=f"{scheme}://api.example.com/a", scheme=scheme, host="api.example.com",
                            port=443 if scheme == "https" else 80, path_query="/a",
                            addresses=["93.184.215.14"])


def test_head_never_reads_a_body(monkeypatch):
    response = _FakeResponse(402, [("WWW-Authenticate", "L402 fixture-string")], b"fixture-string-body")
    conn = _FakeConnection(response)
    monkeypatch.setattr(l402_http, "_open_connection", lambda target, timeout: conn)
    result = l402_http.pinned_transport(_target(), "HEAD", {}, None, 5.0)
    assert result.status == 402
    assert result.body == b""
    assert response.read_sizes == []
    assert conn.closed and response.closed


def test_the_body_is_truncated_at_the_cap(monkeypatch):
    response = _FakeResponse(200, [], b"x" * (l402_http.MAX_BODY_BYTES + 5000))
    conn = _FakeConnection(response)
    monkeypatch.setattr(l402_http, "_open_connection", lambda target, timeout: conn)
    result = l402_http.pinned_transport(_target(), "GET", {}, None, 5.0)
    assert len(result.body) == l402_http.MAX_BODY_BYTES
    assert result.truncated is True
    assert sum(response.read_sizes) == l402_http.MAX_BODY_BYTES + 1
    assert max(response.read_sizes) <= l402_http.READ_CHUNK_BYTES


def test_a_body_under_the_cap_is_not_truncated(monkeypatch):
    response = _FakeResponse(200, [], b"fixture-string-body")
    monkeypatch.setattr(l402_http, "_open_connection", lambda target, timeout: _FakeConnection(response))
    result = l402_http.pinned_transport(_target(), "GET", {}, None, 5.0)
    assert result.body == b"fixture-string-body"
    assert result.truncated is False


def test_body_chunks_are_bounded_by_the_deadline(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(l402_http, "_clock", clock)

    def slow_drip():
        clock.now += 2

    response = _FakeResponse(200, [], b"x" * (l402_http.READ_CHUNK_BYTES * 10), on_read=slow_drip)
    conn = _FakeConnection(response)
    monkeypatch.setattr(l402_http, "_open_connection", lambda target, timeout: conn)
    with pytest.raises(TimeoutError, match="no response within 5 s"):
        l402_http.pinned_transport(_target(), "GET", {}, None, 5.0)
    timeouts = conn.sock.timeouts
    assert timeouts[0] == pytest.approx(5)
    assert timeouts == sorted(timeouts, reverse=True)
    assert all(t > 0 for t in timeouts)
    assert len(response.read_sizes) == 3


def test_the_tls_wrap_verifies_the_vetted_host_name(monkeypatch):
    seen = {}

    class _Raw:
        def close(self):
            seen["raw_closed"] = True

    class _Context:
        def wrap_socket(self, raw, server_hostname=None):
            seen["server_hostname"] = server_hostname
            raise ssl.SSLCertVerificationError("fixture-string-handshake-refused")

    def fake_connect(address, timeout=None, *args, **kwargs):
        seen["address"] = address
        return _Raw()

    monkeypatch.setattr(l402_http.socket, "create_connection", fake_connect)
    monkeypatch.setattr(l402_http.ssl, "create_default_context", lambda: _Context())
    with pytest.raises(ssl.SSLError):
        l402_http.pinned_transport(_target(), "GET", {}, None, 5.0)
    assert seen == {"address": ("93.184.215.14", 443), "server_hostname": "api.example.com", "raw_closed": True}


def test_the_user_agent_says_it_never_pays():
    assert l402_http.USER_AGENT.endswith("; unpaid probe, never pays)")


class _LoopbackServer(http.server.HTTPServer):
    """HTTPServer without the reverse lookup that server_bind does through getfqdn."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(402)
        self.send_header("WWW-Authenticate", 'L402 macaroon="fixture-string-macaroon", invoice="fixture-string-invoice"')
        self.send_header("WWW-Authenticate", 'Payment id="fixture-string-id"')
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_pinned_transport_against_a_loopback_server():
    server = _LoopbackServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/paid"
        result = l402_http.probe(url, allow_private=True)
    finally:
        server.shutdown()
        server.server_close()
    assert result.error_kind is None
    assert result.response.status == 402
    assert len(result.response.header_values("WWW-Authenticate")) == 2
    assert result.response.body == b"{}"


def test_loopback_server_is_refused_without_the_flag():
    result = l402_http.probe("http://127.0.0.1:9/paid")
    assert result.error_kind == "refused"
    assert result.error_reason == "private_address"
