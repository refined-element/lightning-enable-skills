"""The l402_check.py command line, both modes. DNS and HTTP are faked; nothing pays."""
import ast
import io
import json
import subprocess
import sys

import pytest

import l402_check_support as support
import l402_check

SEED_1_HASH = "65e0276b37174dbbdfecc0de804298820c9bb69500d080314b7cc6609d82c88c"
SCRIPT = support.SCRIPTS / "l402_check.py"


def run(argv, fixture=None, **kwargs):
    out = io.StringIO()
    if fixture is not None:
        kwargs.setdefault("resolver", support.fake_resolver(fixture.get("dns", {})))
        kwargs.setdefault("transport", support.fake_transport(fixture["responses"]))
        kwargs.setdefault("now", support.observed(fixture))
    code = l402_check.main(argv, stdout=out, **kwargs)
    return code, out.getvalue()


def test_markdown_is_the_default_and_json_is_available():
    fixture = support.load_fixture("le-test-ping")
    code, markdown = run([fixture["request"]["url"]], fixture)
    assert code == 0
    assert markdown.startswith("# L402 Compatibility Report\n")
    code, text = run([fixture["request"]["url"], "--json"], fixture)
    assert code == 0
    assert json.loads(text)["classification"] == "CHALLENGE_COMPATIBLE"


def test_method_and_max_sats_flags():
    fixture = support.load_fixture("le-test-ping")
    _, text = run([fixture["request"]["url"], "--method", "head", "--max-sats", "5", "--json"], fixture)
    report = json.loads(text)
    assert report["target"]["method"] == "HEAD"
    assert report["preflight"]["max_sats"] == 5


def test_the_report_carries_rerun_notes():
    fixture = support.load_fixture("le-test-ping")
    _, text = run([fixture["request"]["url"], "--json"], fixture)
    assert json.loads(text)["rerun"] == []
    _, markdown = run([fixture["request"]["url"]], fixture)
    assert "## Rerun notes" in markdown


def test_the_user_agent_says_the_check_never_pays():
    fixture = support.load_fixture("le-test-ping")
    log = []
    run([fixture["request"]["url"], "--json"], fixture, transport=support.fake_transport(fixture["responses"], log))
    assert log and all("never pays" in entry["headers"]["User-Agent"] for entry in log)


def test_the_script_has_no_payment_code_path():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert imported <= {"__future__", "argparse", "json", "re", "sys", "datetime", "pathlib", "urllib",
                        "l402_analyze", "l402_evidence", "l402_http", "l402_report"}


# 4. A private-network URL is refused by default.
@pytest.mark.parametrize("url", ["https://192.168.1.20/paid", "https://localhost/paid", "https://169.254.169.254/latest"])
def test_private_url_is_refused_by_default(url):
    log = []
    code, text = run([url, "--json"], transport=support.fake_transport([], log))
    report = json.loads(text)
    assert code == 0
    assert report["classification"] == "INCONCLUSIVE"
    assert report["transport"]["error"] == "refused"
    assert log == []


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/paid", "https://192.168.1.20/paid", "http://[fe80::1]/paid"])
def test_allow_private_admits_local_targets_and_plain_http_to_them(url):
    log = []
    code, text = run([url, "--allow-private", "--json"], transport=support.fake_transport([], log))
    report = json.loads(text)
    assert code == 0
    assert report["transport"]["error"] is None
    assert len(log) == 1


@pytest.mark.parametrize("url", ["https://169.254.169.254/latest", "http://169.254.169.254/latest",
                                 "https://metadata.google.internal/computeMetadata", "http://api.example.com/paid"])
def test_allow_private_never_admits_metadata_or_plain_http_to_a_public_host(url):
    log = []
    code, text = run([url, "--allow-private", "--json"], resolver=support.fake_resolver({}),
                     transport=support.fake_transport([], log))
    report = json.loads(text)
    assert code == 0
    assert report["classification"] == "INCONCLUSIVE"
    assert report["transport"]["error"] == "refused"
    assert log == []


@pytest.mark.parametrize("url", ["https://[::1/paid", "https://[fixture-string-host]/paid"])
def test_a_malformed_bracketed_host_is_a_no_host_refusal(url):
    log = []
    code, text = run([url, "--json"], transport=support.fake_transport([], log))
    report = json.loads(text)
    assert code == 0
    assert report["classification"] == "INCONCLUSIVE"
    assert report["transport"]["error"] == "refused"
    assert [f["code"] for f in report["findings"]] == ["refused_target"]
    assert "no valid host" in report["findings"][0]["message"]
    assert log == []
    code, markdown = run([url], transport=support.fake_transport([], log))
    assert code == 0
    assert "- Error: refused" in markdown


def test_a_malformed_redirect_location_is_reported_like_any_refused_redirect():
    url = "https://api.example.com/paid"
    responses = [{"url": url, "status": 302, "headers": [["Location", "https://[::1/fixture-string-loc"]], "body": ""}]
    for extra in ([], ["--json"]):
        code, text = run([url, *extra], resolver=support.fake_resolver({}),
                         transport=support.fake_transport(responses))
        assert code == 0
        assert "INCOMPATIBLE" in text
        assert "redirect_refused" in text
        assert "fixture-string-loc" not in text


def test_sensitive_query_values_are_redacted():
    fixture = support.load_fixture("le-test-ping")
    url = fixture["request"]["url"] + "?api_key=fixture-string-query-key&city=paris"
    fixture["responses"][0]["url"] = url
    _, text = run([url, "--json", "--header", "Accept=application/json"], fixture)
    report = json.loads(text)
    assert report["target"]["url"] == "https://api.lightningenable.com/l402/test/ping?api_key=REDACTED&city=paris"
    assert report["target"]["headers"] == {"Accept": "application/json"}
    assert "fixture-string-query-key" not in text


@pytest.mark.parametrize("header", [
    "Authorization=Bearer fixture-string-bearer",
    "Cookie=sid=fixture-string-cookie",
    "X-Api-Key=fixture-string-api-key",
    "Host=fixture-string-host.example",
    "Transfer-Encoding=fixture-string-chunked",
    "X-Note=fixture-string-crlf\r\nX-Injected: 1",
    "X-Note=fixture-string-lf\nX-Injected: 1",
    "X-Note=fixture-string-nul\0",
    "X-Note=fixture-string-wide-\N{CJK UNIFIED IDEOGRAPH-4E2D}",
])
def test_credential_framing_and_unsendable_headers_are_refused_without_echoing_the_value(header, capsys):
    fixture = support.load_fixture("le-test-ping")
    log = []
    code, text = run([fixture["request"]["url"], "--header", header], fixture,
                     transport=support.fake_transport(fixture["responses"], log))
    assert code == 2
    assert text == ""
    assert log == []
    err = capsys.readouterr().err
    assert "refusing to send the header" in err
    assert "fixture-string" not in err


def test_body_is_sent_but_never_printed():
    fixture = support.load_fixture("le-test-ping")
    log = []
    _, text = run([fixture["request"]["url"], "--method", "GET", "--body", "fixture-string-private-body", "--json"],
                  fixture, transport=support.fake_transport(fixture["responses"], log))
    assert log[0]["body"] == b"fixture-string-private-body"
    assert "fixture-string-private-body" not in text
    assert json.loads(text)["target"]["body"] == "provided (27 bytes, not shown)"


@pytest.mark.parametrize("argv", [[], ["https://api.example.com/x", "--timeout", "0"],
                                  ["https://api.example.com/x", "--timeout", "31"],
                                  ["https://api.example.com/x", "--timeout", "nan"],
                                  ["https://api.example.com/x", "--max-sats", "0"],
                                  ["https://api.example.com/x", "--header", "no-equals-sign"],
                                  ["https://api.example.com/x", "--header", "=value"],
                                  ["https://api.example.com/x", "--method", "GE T"],
                                  ["https://api.example.com/x", "--mode-a", "mode-a.json"],
                                  ["https://api.example.com/x", "--credential-stdin"],
                                  ["https://api.example.com/x", "--evidence", "evidence.json"]])
def test_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as caught:
        l402_check.main(argv, stdout=io.StringIO())
    assert caught.value.code == 2


def test_help_lists_every_flag_and_the_exit_codes():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    for flag in ("url", "--method", "--header", "--body", "--timeout", "--max-sats", "--json", "--allow-private",
                 "--evidence", "--mode-a", "--credential-stdin"):
        assert flag in result.stdout
    assert "Exit status" in result.stdout
    assert "non-secret" in result.stdout
    assert "\N{EM DASH}" not in result.stdout


def test_a_refused_target_from_the_shell_prints_an_inconclusive_report():
    result = subprocess.run([sys.executable, str(SCRIPT), "https://192.168.1.20/paid"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert "- Classification: INCONCLUSIVE" in result.stdout
    assert "- Error: refused" in result.stdout


def _evidence_files(tmp_path):
    report, _ = support.run_fixture(support.load_fixture("le-test-ping"))
    evidence = support.load_evidence("fulfilled-2xx")
    preimage = support.preimage_from_seed(evidence.pop("test_preimage_seed"))
    (tmp_path / "mode-a.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return tmp_path / "evidence.json", tmp_path / "mode-a.json", preimage


class CountingStdin(io.StringIO):
    """Counts every read, so a test can prove stdin is read exactly once, or never."""

    def __init__(self, text=""):
        super().__init__(text)
        self.reads = 0

    def read(self, *args):
        self.reads += 1
        return super().read(*args)

    def readline(self, *args):
        self.reads += 1
        return super().readline(*args)

    def __iter__(self):
        raise AssertionError("stdin must be read with one read() call")


def test_evidence_mode_reads_the_credential_from_stdin_and_never_prints_it(tmp_path):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    token = f"L402 fixture-string-macaroon:{preimage}"
    for extra in ([], ["--json"]):
        code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin", *extra],
                         stdin=io.StringIO(token + "\n"))
        assert code == 0
        assert "FULFILLMENT_VERIFIED" in text
        assert preimage not in text
        assert "fixture-string-macaroon" not in text
        assert SEED_1_HASH in text


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"])
def test_the_credential_is_read_once_and_one_trailing_newline_is_stripped(tmp_path, ending):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    stdin = CountingStdin(f"L402 fixture-string-macaroon:{preimage.upper()}{ending}")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin", "--json"],
                     stdin=stdin)
    assert code == 0
    assert stdin.reads == 1
    report = json.loads(text)
    assert report["classification"] == "FULFILLMENT_VERIFIED"
    assert preimage not in text.lower()
    # Nothing is written to disk: the files are exactly what the test wrote.
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_without_credential_stdin_stdin_is_never_read(tmp_path):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    stdin = CountingStdin("fixture-string-not-a-credential\n")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--json"], stdin=stdin)
    assert code == 0
    assert stdin.reads == 0
    report = json.loads(text)
    assert report["classification"] == "INCONCLUSIVE"
    assert "preimage_unchecked" in {f["code"] for f in report["findings"]}


def test_evidence_mode_without_a_credential_is_inconclusive(tmp_path):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--json"])
    assert code == 0
    assert json.loads(text)["classification"] == "INCONCLUSIVE"


def test_an_empty_credential_on_stdin_is_inconclusive(tmp_path):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin", "--json"],
                     stdin=io.StringIO("\n"))
    assert code == 0
    assert "preimage_unchecked" in {f["code"] for f in json.loads(text)["findings"]}


def test_evidence_with_the_read_only_report_inside_needs_no_mode_a_flag(tmp_path):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    data = json.loads(evidence.read_text(encoding="utf-8"))
    data["mode_a_report"] = json.loads(mode_a.read_text(encoding="utf-8"))
    evidence.write_text(json.dumps(data), encoding="utf-8")
    code, text = run(["--evidence", str(evidence), "--json"])
    assert code == 0
    assert json.loads(text)["mode"] == "paid"


def test_a_read_only_report_in_both_places_is_an_evidence_error(tmp_path, capsys):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    data = json.loads(evidence.read_text(encoding="utf-8"))
    data["mode_a_report"] = {"preimage": "fixture-string-credential"}
    evidence.write_text(json.dumps(data), encoding="utf-8")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a)])
    assert code == 2
    assert text == ""
    err = capsys.readouterr().err
    assert "evidence error" in err
    assert "fixture-string-credential" not in err


def test_the_evidence_file_credential_refusal_runs_after_the_mode_a_merge(tmp_path, capsys):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    data = json.loads(evidence.read_text(encoding="utf-8"))
    data["tool_result"]["l402_token"] = "fixture-string-credential"
    evidence.write_text(json.dumps(data), encoding="utf-8")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin"],
                     stdin=io.StringIO(f"L402 fixture-string-macaroon:{preimage}\n"))
    assert code == 2
    assert text == ""
    err = capsys.readouterr().err
    assert "looks like a credential" in err
    assert "fixture-string" not in err
    assert preimage not in err


def test_credential_stdin_needs_the_evidence_in_a_file(capsys):
    code, text = run(["--evidence", "-", "--credential-stdin"], stdin=io.StringIO("{}"))
    assert code == 2
    assert text == ""
    assert "evidence error" in capsys.readouterr().err


@pytest.mark.parametrize("content, wanted", [
    (b"{ fixture-string-not-json", "not valid JSON"),
    (b"\xff\xfe fixture-string-binary", "not UTF-8"),
])
def test_unreadable_files_are_evidence_errors_without_echoing_content(tmp_path, capsys, content, wanted):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    for target in (evidence, mode_a):
        original = target.read_bytes()
        target.write_bytes(content)
        code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a)])
        target.write_bytes(original)
        assert code == 2
        assert text == ""
        err = capsys.readouterr().err
        assert wanted in err
        assert "fixture-string" not in err


def test_a_missing_file_is_an_evidence_error(tmp_path, capsys):
    code, _ = run(["--evidence", str(tmp_path / "absent.json")])
    assert code == 2
    assert "evidence error" in capsys.readouterr().err


def test_evidence_error_exits_2_without_echoing_values(tmp_path, capsys):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"preimage": "fixture-string-credential"}), encoding="utf-8")
    code, _ = run(["--evidence", str(path)])
    assert code == 2
    err = capsys.readouterr().err
    assert "evidence error" in err
    assert "fixture-string-credential" not in err
