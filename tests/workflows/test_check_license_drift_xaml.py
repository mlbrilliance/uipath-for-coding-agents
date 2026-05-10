"""Static structural assertions for CheckLicenseDrift.xaml.

T-C8 / US-38 / D6 acceptance test.

The workflow is XAML, which is XML. We cannot execute it from CPython
(it needs the Windows-Workflow runtime via UiPath Studio/Robot), so we
verify the activity *tree* meets REFramework discipline:

- Try/Catch wraps each HTTP call (R.E.01).
- RetryScope is present with the right attributes (R.E.02).
- 4xx auth failures are not retried (R.E.03) - witnessed as an explicit
  bail-out branch on the GitHub call.
- GitHubToken via GetRobotCredential, never inline (R.X.02).
- API base URLs come from Config.xlsx::Settings via GetAsset (R.C.01) -
  i.e. only the two API host strings appear in the file, no other
  hardcoded production hostnames.
- Logging bookends "Starting CheckLicenseDrift" / "Completed CheckLicenseDrift" (R.L.01).
- Argument prefixes match (R.N.02).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
XAML_PATH = (
    REPO_ROOT
    / "examples/oss-supply-chain-defender/workflows/License/CheckLicenseDrift.xaml"
)

# XAML namespace URIs we tolerate in the file.  These are *namespace*
# identifiers, not API endpoints - they never resolve at runtime.
ALLOWED_NS_URIS = {
    "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation",
    "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
    "http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger",
    "http://schemas.uipath.com/workflow/activities",
    "http://schemas.microsoft.com/winfx/2006/xaml",
}

# The two endpoint *hosts* we expect to find in the file.
CLEARLYDEFINED_PREFIX = "https://api.clearlydefined.io"
GITHUB_API_PREFIX = "https://api.github.com"

ACT_NS = "{http://schemas.microsoft.com/netfx/2009/xaml/activities}"
UI_NS = "{http://schemas.uipath.com/workflow/activities}"


def _load_xml() -> ET.ElementTree:
    assert XAML_PATH.exists(), f"missing workflow: {XAML_PATH}"
    return ET.parse(XAML_PATH)


def _iter_local(tree: ET.ElementTree, local_name: str) -> list[ET.Element]:
    """Return every element whose local name (without namespace) matches."""
    found: list[ET.Element] = []
    for elem in tree.iter():
        tag = elem.tag.split("}", 1)[-1]
        if tag == local_name:
            found.append(elem)
    return found


def test_xaml_parses_as_xml() -> None:
    """Sanity: the file is well-formed XML (XAML is XML)."""
    _load_xml()  # raises ParseError on failure


def test_workflow_opens_and_closes_with_log_messages() -> None:
    tree = _load_xml()
    log_messages = _iter_local(tree, "LogMessage")
    msgs = [
        elem.attrib.get("Message", "")
        for elem in log_messages
    ]
    assert any("Starting CheckLicenseDrift" in m for m in msgs), (
        f"R.L.01: missing 'Starting CheckLicenseDrift' log; saw {msgs!r}"
    )
    assert any("Completed CheckLicenseDrift" in m for m in msgs), (
        f"R.L.01: missing 'Completed CheckLicenseDrift' log; saw {msgs!r}"
    )


def test_argument_naming_uses_prefixes() -> None:
    tree = _load_xml()
    props = _iter_local(tree, "Property")
    names = [p.attrib.get("Name", "") for p in props]
    assert "in_dt_Lockfiles" in names, f"R.N.02: missing in_dt_Lockfiles in {names!r}"
    assert "out_dt_Conflicts" in names, f"R.N.02: missing out_dt_Conflicts in {names!r}"
    for name in names:
        assert name.startswith(("in_", "out_", "io_")), (
            f"R.N.02: argument {name!r} lacks direction prefix"
        )


def test_each_http_call_is_wrapped_in_try_catch_and_retry_scope() -> None:
    """R.E.01 + R.E.02: every HttpClient sits under at least one TryCatch and
    one RetryScope ancestor."""
    tree = _load_xml()
    root = tree.getroot()

    # Build a parent-map so we can walk ancestors.
    parent_map = {child: parent for parent in root.iter() for child in parent}

    http_calls = _iter_local(tree, "HttpClient")
    assert len(http_calls) >= 2, (
        f"expected at least 2 HttpClient activities (primary + fallback), got {len(http_calls)}"
    )

    for http in http_calls:
        ancestors_local: list[str] = []
        cur = parent_map.get(http)
        while cur is not None:
            ancestors_local.append(cur.tag.split("}", 1)[-1])
            cur = parent_map.get(cur)
        assert "TryCatch" in ancestors_local, (
            f"R.E.01: HttpClient at endpoint "
            f"{http.attrib.get('Endpoint')} not inside a TryCatch; "
            f"ancestors: {ancestors_local}"
        )
        assert "RetryScope" in ancestors_local, (
            f"R.E.02: HttpClient at endpoint "
            f"{http.attrib.get('Endpoint')} not inside a RetryScope; "
            f"ancestors: {ancestors_local}"
        )


def test_retry_scope_uses_three_retries_with_five_second_interval() -> None:
    tree = _load_xml()
    retries = _iter_local(tree, "RetryScope")
    assert retries, "R.E.02: no RetryScope present"
    for r in retries:
        assert r.attrib.get("NumberOfRetries") == "3", (
            f"R.E.02: RetryScope NumberOfRetries={r.attrib.get('NumberOfRetries')} (want 3)"
        )
        assert r.attrib.get("RetryInterval") == "00:00:05", (
            f"R.E.02: RetryScope RetryInterval={r.attrib.get('RetryInterval')} (want 00:00:05)"
        )


def test_no_retry_on_auth_4xx() -> None:
    """R.E.03: the file contains an explicit 'bail on 4xx' branch in the
    GitHub-call retry, so retries are skipped on auth failures."""
    text = XAML_PATH.read_text(encoding="utf-8")
    assert "GitHub Licenses auth failure" in text, (
        "R.E.03: expected an explicit auth-failure short-circuit on the GitHub call"
    )
    # And the primary ClearlyDefined call also bails on 4xx so transient
    # 404s aren't retried 3x before falling back.
    assert "Bail on 4xx" in text, (
        "R.E.03: expected an explicit 4xx bail-out branch"
    )


def test_github_token_via_get_robot_credential() -> None:
    tree = _load_xml()
    creds = _iter_local(tree, "GetRobotCredential")
    asset_names = [c.attrib.get("AssetName") for c in creds]
    assert "GitHubToken" in asset_names, (
        f"R.X.02: GetRobotCredential('GitHubToken') missing; saw {asset_names!r}"
    )

    # Belt-and-braces: the literal token must NOT appear inline anywhere.
    text = XAML_PATH.read_text(encoding="utf-8")
    forbidden = re.compile(r"(ghp_|github_pat_)[A-Za-z0-9_]+")
    assert not forbidden.search(text), (
        "R.X.02: a literal GitHub token pattern was found inline"
    )


def test_url_bases_come_from_config_via_get_asset() -> None:
    tree = _load_xml()
    assets = _iter_local(tree, "GetAsset")
    asset_names = [a.attrib.get("AssetName") for a in assets]
    assert "ClearlyDefinedApiBase" in asset_names, (
        f"R.C.01: missing GetAsset('ClearlyDefinedApiBase'); saw {asset_names!r}"
    )
    assert "GitHubApiBase" in asset_names, (
        f"R.C.01: missing GetAsset('GitHubApiBase'); saw {asset_names!r}"
    )


def test_clearlydefined_url_prefix_present() -> None:
    """The canonical URL must be documented in the file (in the header
    comment) so reviewers can see exactly which API is being called.  At
    runtime the base comes from GetAsset('ClearlyDefinedApiBase') - this
    test only enforces that the literal default URL is referenced."""
    text = XAML_PATH.read_text(encoding="utf-8")
    assert CLEARLYDEFINED_PREFIX in text, (
        f"expected literal {CLEARLYDEFINED_PREFIX} as documentation marker"
    )
    # And the asset name must also be present.
    assert "ClearlyDefinedApiBase" in text


def test_github_api_url_prefix_present() -> None:
    text = XAML_PATH.read_text(encoding="utf-8")
    assert GITHUB_API_PREFIX in text, (
        f"expected literal {GITHUB_API_PREFIX} (fallback API base) in file"
    )
    assert "GitHubApiBase" in text


def test_url_path_templates_present_for_both_apis() -> None:
    """Even though the host is Config-driven, the *path template* for each
    API must appear in the file so the right endpoint is being composed."""
    text = XAML_PATH.read_text(encoding="utf-8")
    # ClearlyDefined: /definitions/{type}/{provider}/{namespace}/{name}/{revision}
    assert "/definitions/" in text, (
        "ClearlyDefined path template /definitions/ not found"
    )
    # GitHub Licenses: /repos/{owner}/{repo}/license
    assert "/repos/" in text and "/license" in text, (
        "GitHub Licenses path template /repos/.../license not found"
    )


def test_no_other_hardcoded_https_hosts() -> None:
    """Only two production hosts are allowed - the ClearlyDefined.io and
    GitHub API bases (which appear as documentation markers in the header
    comment).  Everything else must be either an XAML/XML namespace URI or
    absent.  Runtime URLs are composed from Config (R.C.01)."""
    text = XAML_PATH.read_text(encoding="utf-8")
    https_urls = set(re.findall(r"https?://[^\s\"'<>\]]+", text))
    allowed_hosts = {
        CLEARLYDEFINED_PREFIX,
        GITHUB_API_PREFIX,
    }
    offenders: list[str] = []
    for url in https_urls:
        if url in ALLOWED_NS_URIS:
            continue
        # Allow the two documented API bases and any path under them
        # (e.g., the comment may reference the path template).
        if any(url.startswith(host) for host in allowed_hosts):
            continue
        offenders.append(url)
    assert not offenders, (
        "Unexpected hardcoded URLs in CheckLicenseDrift.xaml:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_output_table_has_required_columns() -> None:
    text = XAML_PATH.read_text(encoding="utf-8")
    for col in ("Package", "DeclaredLicense", "TransitiveLicense", "ConflictType"):
        assert f'ColumnName="{col}"' in text, (
            f"out_dt_Conflicts schema missing column {col!r}"
        )
