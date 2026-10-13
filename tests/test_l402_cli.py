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


@pytest.mark.parametrize("header", ["Authorization: Bearer fixtureSECRETtoken==",
                                    "X-Note fixtureSECRETtoken=v", "fixtureSECRETtoken:=v"])
def test_a_curl_style_header_is_a_usage_error_that_echoes_nothing(header, capsys):
    out = io.StringIO()
    with pytest.raises(SystemExit) as caught:
        l402_check.main(["https://api.example.com/x", "--header", header], stdout=out)
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "header must be NAME=VALUE with a token name" in captured.err
    for text in (captured.err, captured.out, out.getvalue()):
        assert "fixtureSECRET" not in text
        assert "Bearer" not in text


@pytest.mark.parametrize("reason", ["credential_header", "reserved_header", "invalid_header_name",
                                    "invalid_header_value", "fixture-string-unknown"])
def test_refusal_messages_are_fixed_text_and_name_only_a_token_header(reason):
    refused = l402_check.l402_http.RefusedHeaderError("Bad Name: fixture-string-secret", reason,
                                                      "fixture-string-secret in the message")
    message = l402_check.refusal_message(refused)
    assert "fixture-string" not in message
    assert message.startswith("refusing to send a header: ")
    named = l402_check.l402_http.RefusedHeaderError("X-Api-Key", reason, "fixture-string-secret")
    assert l402_check.refusal_message(named).startswith("refusing to send the header X-Api-Key: ")


def test_skill_md_and_help_list_every_refused_header_fragment():
    skill = (support.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    step0 = skill.split("### 0. Ask what to check", 1)[1].split("\n### ", 1)[0]
    helptext = l402_check.build_parser().format_help()
    for fragment in l402_check.l402_http.CREDENTIAL_HEADER_FRAGMENTS:
        assert f"`{fragment}`" in step0
        assert fragment in helptext
    for name in ("Authorization", "Cookie", "Proxy-Authorization", "Host", "Content-Length",
                 "Transfer-Encoding", "Connection"):
        assert f"`{name}`" in step0


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
                                  ["https://api.example.com/x", "--evidence", "evidence.json"],
                                  ["https://api.example.com/x", "--profile", "other"],
                                  ["--evidence", "evidence.json", "--profile", "amazap"]])
def test_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as caught:
        l402_check.main(argv, stdout=io.StringIO())
    assert caught.value.code == 2


def test_help_lists_every_flag_and_the_exit_codes():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    for flag in ("url", "--method", "--header", "--body", "--timeout", "--max-sats", "--json", "--allow-private",
                 "--evidence", "--mode-a", "--credential-stdin", "--output", "--profile"):
        assert flag in result.stdout
    assert "Exit status" in result.stdout
    assert "non-secret" in result.stdout
    assert "\N{EM DASH}" not in result.stdout


def test_an_unknown_profile_is_a_usage_error_that_never_echoes_the_name(capsys):
    with pytest.raises(SystemExit) as caught:
        l402_check.main(["https://api.example.com/x", "--profile", "fixture-string-profile"], stdout=io.StringIO())
    assert caught.value.code == 2
    err = capsys.readouterr().err
    assert "the profile must be one of: amazap" in err
    assert "fixture-string-profile" not in err


def test_the_amazap_profile_flag_is_the_only_way_to_probe_the_host_root():
    fixture = support.load_fixture("l402kit-worldstate-single-l402")
    with_flag, without_flag = [], []
    run([fixture["request"]["url"], "--json", "--profile", "amazap"], fixture,
        transport=support.fake_transport(fixture["responses"], with_flag))
    code, text = run([fixture["request"]["url"], "--json"], fixture,
                     transport=support.fake_transport(fixture["responses"], without_flag))
    assert len(with_flag) == 3
    assert len(without_flag) == 1
    assert code == 0
    assert json.loads(text)["marketplace_profiles"]["amazap"]["status"] == "NOT_CHECKED"


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


@pytest.mark.parametrize("flags", [["--evidence", "-"], ["--evidence", "EVIDENCE", "--mode-a", "-"],
                                   ["--evidence", "-", "--mode-a", "-"]])
def test_stdin_is_never_a_file_so_the_credential_is_read_at_most_once(tmp_path, capsys, flags):
    evidence, _, preimage = _evidence_files(tmp_path)
    flags = [str(evidence) if f == "EVIDENCE" else f for f in flags]
    stdin = CountingStdin(f"L402 fixture-string-macaroon:{preimage}\n")
    code, text = run([*flags, "--credential-stdin"], stdin=stdin)
    assert code == 2
    assert text == ""
    assert stdin.reads == 0
    err = capsys.readouterr().err
    assert "file paths, not -" in err
    assert preimage not in err
    assert "fixture-string" not in err


class TerminalStdin(CountingStdin):
    def isatty(self):
        return True


def test_the_credential_is_never_read_from_a_terminal(tmp_path, capsys):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    stdin = TerminalStdin("fixture-string-typed\n")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin"], stdin=stdin)
    assert code == 2
    assert text == ""
    assert stdin.reads == 0
    err = capsys.readouterr().err
    assert "evidence error" in err
    assert "terminal" in err


def test_a_terminal_stdin_is_fine_without_credential_stdin(tmp_path):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    stdin = TerminalStdin("")
    code, _ = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--json"], stdin=stdin)
    assert code == 0
    assert stdin.reads == 0


@pytest.mark.parametrize("key, value", [
    ("target", []), ("target", {"url": "x"}), ("transport", []), ("challenge", "fixture-string-x"),
    ("invoice", []), ("binding", 5), ("marketplace_profiles", []), ("marketplace_profiles", {"amazap": {"checks": 5}}), ("marketplace_profiles", {"amazap": {"checks": [1]}}), ("marketplace_profiles", {"fixture-string-x": {}}),
    ("marketplace_profiles", {}), ("marketplace_profiles", {"amazap": {"checks": []}}),
    ("marketplace_profiles", {"amazap": {"checks": [{}]}}), ("marketplace_profiles", {"amazap": {}}),
    ("marketplace_profiles", {"amazap": {"checks": [{"name": "fixture-string-x", "pass": True, "required": True,
                                                     "detail": "fixture-string-x"}]}}),
    ("findings", 5), ("findings", ["fixture-string-x"]), ("evidence", []), ("rerun", "x"),
])
def test_a_malformed_read_only_report_is_an_evidence_error_not_a_traceback(tmp_path, capsys, key, value):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    report = json.loads(mode_a.read_text(encoding="utf-8"))
    report[key] = value
    mode_a.write_text(json.dumps(report), encoding="utf-8")
    for extra in ([], ["--json"]):
        code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin", *extra],
                         stdin=io.StringIO(f"L402 fixture-string-macaroon:{preimage}\n"))
        err = capsys.readouterr().err
        assert code == 2
        assert text == ""
        assert f"evidence error: evidence.mode_a_report.{key}" in err
        assert preimage not in err
        assert "fixture-string" not in err


# Shapes _require accepts but the Markdown renderer can't use: still an evidence error, never a traceback.
@pytest.mark.parametrize("key", ["transport", "challenge"])
def test_a_report_the_renderer_cannot_use_is_an_evidence_error(tmp_path, capsys, key):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    report = json.loads(mode_a.read_text(encoding="utf-8"))
    report[key] = {"fixture-string-field": "fixture-string-value"}
    mode_a.write_text(json.dumps(report), encoding="utf-8")
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin"],
                     stdin=io.StringIO(f"L402 fixture-string-macaroon:{preimage}\n"))
    err = capsys.readouterr().err
    assert code == 2
    assert text == ""
    assert "evidence error" in err and "wrong shape" in err
    assert preimage not in err
    assert "fixture-string" not in err


@pytest.mark.parametrize("content, wanted", [
    (b"{ fixture-string-not-json", "not valid JSON"),
    (b"\x80\x81 fixture-string-binary", "not UTF-8 or UTF-16 text"),
    (b"\xff\xfe" + "fixture-string-odd".encode("utf-16-le") + b"\x41", "not UTF-8 or UTF-16 text"),
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


@pytest.mark.parametrize("encoding, bom", [
    ("utf-16-le", b"\xff\xfe"),  # what Windows PowerShell 5.1 writes for "> mode-a.json"
    ("utf-16-be", b"\xfe\xff"),
    ("utf-8", b"\xef\xbb\xbf"),
])
def test_files_with_a_byte_order_mark_load(tmp_path, encoding, bom):
    evidence, mode_a, preimage = _evidence_files(tmp_path)
    for target in (evidence, mode_a):
        target.write_bytes(bom + target.read_text(encoding="utf-8").encode(encoding))
    code, text = run(["--evidence", str(evidence), "--mode-a", str(mode_a), "--credential-stdin", "--json"],
                     stdin=io.StringIO(f"L402 fixture-string-macaroon:{preimage}\n"))
    assert code == 0
    assert json.loads(text)["classification"] == "FULFILLMENT_VERIFIED"


def test_output_writes_utf8_that_the_paid_check_reads_back(tmp_path):
    fixture = support.load_fixture("le-test-ping")
    saved = tmp_path / "mode-a.json"
    code, text = run([fixture["request"]["url"], "--max-sats", "50", "--json", "--output", str(saved)], fixture)
    assert code == 0
    assert text == f"Wrote the report to {saved}.\n"
    raw = saved.read_bytes()
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf"))
    assert b"\r\n" not in raw
    assert json.loads(raw.decode("utf-8"))["classification"] == "CHALLENGE_COMPATIBLE"
    paid_dir = tmp_path / "paid"
    paid_dir.mkdir()
    evidence, _, preimage = _evidence_files(paid_dir)
    paid = tmp_path / "paid.md"
    code, text = run(["--evidence", str(evidence), "--mode-a", str(saved), "--credential-stdin", "--output", str(paid)],
                     stdin=io.StringIO(f"L402 fixture-string-macaroon:{preimage}\n"))
    assert code == 0
    assert text == f"Wrote the report to {paid}.\n"
    report = paid.read_text(encoding="utf-8")
    assert "- Classification: FULFILLMENT_VERIFIED" in report
    assert preimage not in report
    assert "fixture-string-macaroon" not in report


@pytest.mark.parametrize("which", ["evidence", "mode_a", "dash", "empty"])
def test_output_never_overwrites_an_input_file(tmp_path, which):
    evidence, mode_a, _ = _evidence_files(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    target = {"evidence": str(evidence), "mode_a": str(mode_a), "dash": "-", "empty": ""}[which]
    with pytest.raises(SystemExit) as caught:
        l402_check.main(["--evidence", str(evidence), "--mode-a", str(mode_a), "--output", target],
                        stdout=io.StringIO())
    assert caught.value.code == 2
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_an_unwritable_output_is_an_error(tmp_path, capsys):
    fixture = support.load_fixture("le-test-ping")
    code, text = run([fixture["request"]["url"], "--json", "--output", str(tmp_path / "missing-dir" / "out.json")],
                     fixture)
    assert code == 2
    assert text == ""
    assert "cannot write the report to --output" in capsys.readouterr().err


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
