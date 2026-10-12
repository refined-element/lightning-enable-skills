"""Target refusal before any connection opens. DNS is faked; nothing touches the network."""
import pytest

import l402_check_support as support
from l402_netsafety import ResolutionError, UnsafeTargetError, resolve_target


def resolver(mapping):
    return support.fake_resolver(mapping)


def test_public_https_target_is_accepted_and_pinned():
    target = resolve_target("https://api.example.com/x?q=1", resolver=resolver({}))
    assert target.addresses == [support.PUBLIC_TEST_ADDRESS]
    assert target.path_query == "/x?q=1"
    assert target.origin == "https://api.example.com"
    assert target.is_public


@pytest.mark.parametrize(
    "url, mapping, reason",
    [
        ("https://localhost/x", {}, "private_address"),
        ("https://127.0.0.1/x", {}, "private_address"),
        ("https://[::1]/x", {}, "private_address"),
        ("https://10.1.2.3/x", {}, "private_address"),
        ("https://172.16.0.9/x", {}, "private_address"),
        ("https://192.168.1.10/x", {}, "private_address"),
        ("https://169.254.10.10/x", {}, "private_address"),
        ("https://[fd12::1]/x", {}, "private_address"),
        ("https://[::ffff:10.0.0.1]/x", {}, "private_address"),
        ("https://internal.example.com/x", {"internal.example.com": ["10.0.0.5"]}, "private_address"),
        ("https://mixed.example.com/x", {"mixed.example.com": [support.PUBLIC_TEST_ADDRESS, "192.168.0.2"]}, "private_address"),
        ("https://169.254.169.254/latest/meta-data", {}, "cloud_metadata"),
        ("https://metadata.google.internal/", {}, "cloud_metadata"),
        ("http://api.example.com/x", {}, "not_https"),
        ("ftp://api.example.com/x", {}, "scheme"),
        ("https://user:pw@api.example.com/x", {}, "credentials_in_url"),
    ],
)
def test_unsafe_targets_are_refused(url, mapping, reason):
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target(url, resolver=resolver(mapping))
    assert caught.value.reason == reason


def test_allow_private_admits_local_targets_and_http_to_them():
    target = resolve_target("http://127.0.0.1:8080/x", allow_private=True)
    assert target.addresses == ["127.0.0.1"]
    assert not target.is_public


def test_allow_private_never_admits_metadata_or_public_http():
    with pytest.raises(UnsafeTargetError):
        resolve_target("http://169.254.169.254/", allow_private=True)
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target("http://api.example.com/", allow_private=True, resolver=resolver({}))
    assert caught.value.reason == "not_https"


def test_unresolvable_host_is_inconclusive_not_refused():
    def failing(host, port):
        raise ResolutionError("could not resolve host")

    with pytest.raises(ResolutionError):
        resolve_target("https://nowhere.example.com/", resolver=failing)
