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


@pytest.mark.parametrize("allow_private", [False, True])
def test_nat64_form_of_metadata_is_refused_even_with_allow_private(allow_private):
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target("https://[64:ff9b::a9fe:a9fe]/", allow_private=allow_private)
    assert caught.value.reason == "cloud_metadata"


def test_nat64_form_of_private_address_needs_allow_private():
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target("https://[64:ff9b::a00:1]/")
    assert caught.value.reason == "private_address"
    target = resolve_target("https://[64:ff9b::a00:1]/", allow_private=True)
    assert not target.is_public


@pytest.mark.parametrize("allow_private", [False, True])
@pytest.mark.parametrize(
    "url",
    [
        "https://[::a9fe:a9fe]/",
        "https://[2002:a9fe:a9fe::1]/",
        "https://[2001:0:4136:e378:8000:63bf:5601:5601]/",
    ],
)
def test_embedded_ipv4_forms_of_metadata_are_refused(url, allow_private):
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target(url, allow_private=allow_private)
    assert caught.value.reason == "cloud_metadata"


def test_ipv4_compatible_form_of_private_address_needs_allow_private():
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target("https://[::a00:1]/")
    assert caught.value.reason == "private_address"
    target = resolve_target("https://[::a00:1]/", allow_private=True)
    assert not target.is_public


def test_resolver_answer_in_nat64_form_is_checked():
    mapping = {"sneaky.example.com": ["64:ff9b::a9fe:a9fe"]}
    with pytest.raises(UnsafeTargetError) as caught:
        resolve_target("https://sneaky.example.com/", resolver=resolver(mapping))
    assert caught.value.reason == "cloud_metadata"


def test_unresolvable_host_is_inconclusive_not_refused():
    def failing(host, port):
        raise ResolutionError("could not resolve host")

    with pytest.raises(ResolutionError):
        resolve_target("https://nowhere.example.com/", resolver=failing)
