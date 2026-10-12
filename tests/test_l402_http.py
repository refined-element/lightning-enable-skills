"""The unpaid probe: vetted addresses, bounded redirects, header hygiene.

HTTP is faked except in the loopback test, which serves one 402 from
127.0.0.1 with --allow-private semantics. Nothing leaves the machine.
"""
import http.server
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
    "X-SESSIONID",
])
def test_credential_header_names_are_refused_before_any_request(name):
    log = []
    with pytest.raises(l402_http.CredentialHeaderError) as caught:
        l402_http.probe("https://api.example.com/a", headers={name: "fixture-string-header-value"},
                        resolver=resolver({}), transport=support.fake_transport([], log))
    assert log == []
    assert caught.value.header_name == name
    assert "fixture-string-header-value" not in str(caught.value)


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
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
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
