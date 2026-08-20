from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools" / "swift-mystandards-downloader" / "swift_mystandards_downloader.py"
SPEC = importlib.util.spec_from_file_location("swift_mystandards_downloader", MODULE_PATH)
assert SPEC and SPEC.loader
downloader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = downloader
SPEC.loader.exec_module(downloader)


def re_search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def test_sanitize_filename_removes_path_and_reserved_characters() -> None:
    assert (
        downloader.sanitize_filename('MT541 Receive/Against:Payment?.pdf')
        == "MT541_Receive_Against_Payment.pdf"
    )
    assert downloader.sanitize_filename("../../secret") == "secret"


def test_default_output_path_uses_home_downloads(tmp_path: Path) -> None:
    assert downloader.default_output_dir(tmp_path) == (
        tmp_path / "Downloads" / "SWIFT_MT_2026_November"
    )


def test_env_file_loading_and_missing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SWIFT_MYSTANDARDS_EMAIL=operator@example.test\n"
        "SWIFT_MYSTANDARDS_PASSWORD='not-printed'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SWIFT_MYSTANDARDS_EMAIL", raising=False)
    monkeypatch.delenv("SWIFT_MYSTANDARDS_PASSWORD", raising=False)
    config = downloader.load_config(["--env-file", str(env_file), "--dry-run"])
    assert config.email == "operator@example.test"
    assert config.password == "not-printed"

    empty = tmp_path / "empty.env"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(downloader.ConfigurationError) as exc:
        downloader.load_config(["--env-file", str(empty)])
    assert "SWIFT_MYSTANDARDS_EMAIL is not configured." in str(exc.value)
    assert "SWIFT_MYSTANDARDS_PASSWORD is not configured." in str(exc.value)


def test_env_file_supports_existing_swift_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SWIFT_EMAIL=operator@example.test\n"
        "SWIFT_PASSWORD='alias-secret'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SWIFT_MYSTANDARDS_EMAIL", raising=False)
    monkeypatch.delenv("SWIFT_MYSTANDARDS_PASSWORD", raising=False)
    monkeypatch.delenv("SWIFT_EMAIL", raising=False)
    monkeypatch.delenv("SWIFT_PASSWORD", raising=False)
    config = downloader.load_config(["--env-file", str(env_file), "--dry-run"])
    assert config.email == "operator@example.test"
    assert config.password == "alias-secret"


def test_auth_state_classification() -> None:
    assert (
        downloader.classify_auth_state_text(
            "https://login.swift.com",
            "Sign in Password",
            has_password_field=True,
            release="2026.November",
        )
        == downloader.AuthState.LOGIN
    )
    assert (
        downloader.classify_auth_state_text(
            "https://www2.swift.com",
            "Two-step verification code",
            has_password_field=False,
            release="2026.November",
        )
        == downloader.AuthState.MFA
    )
    assert (
        downloader.classify_auth_state_text(
            "https://www2.swift.com/mystandards/#/mtcategories/mt/2026.November",
            "Category 5 Securities",
            has_password_field=False,
            release="2026.November",
        )
        == downloader.AuthState.AUTHENTICATED
    )
    assert (
        downloader.classify_auth_state_text(
            "https://www2.swift.com/mystandards/#/mt/2026.November/541/!content",
            "",
            has_password_field=False,
            release="2026.November",
        )
        == downloader.AuthState.AUTHENTICATED
    )


def test_category_and_message_discovery_from_clickables() -> None:
    clickables = [
        downloader.Clickable(
            0,
            "Category 5 Securities Markets",
            "https://x/#/mtcategories/mt/2026.November/5",
            "A",
            "",
            "",
        ),
        downloader.Clickable(
            1,
            "Category 1 Customer Payments",
            "https://x/#/mtcategories/mt/2026.November/1",
            "A",
            "",
            "",
        ),
    ]
    categories = downloader.categories_from_clickables(
        clickables, release="2026.November", source_page="https://x"
    )
    assert [item.category for item in categories] == ["1", "5"]
    assert categories[1].folder_name == "Category_5_Securities_Markets"

    messages = downloader.messages_from_clickables(
        [
            downloader.Clickable(
                0, "MT541 Receive Against Payment", "https://x/MT541", "A", "", ""
            ),
            downloader.Clickable(1, "MT540 Receive Free", "https://x/MT540", "A", "", ""),
        ],
        category=categories[1],
        source_page="https://x/category5",
    )
    assert [item.messageType for item in messages] == ["MT540", "MT541"]
    assert messages[1].messageName == "Receive Against Payment"


def test_count_only_category_labels_and_generic_n_messages() -> None:
    clickables = [
        downloader.Clickable(0, "Category 5 (46)", "", "A", "", ""),
        downloader.Clickable(1, "Category n (7)", "", "A", "", ""),
    ]
    categories = downloader.categories_from_clickables(
        clickables,
        release="2026.November",
        source_page="https://www2.swift.com/mystandards/#/mtcategories/mt/2026.November",
    )
    assert [item.category for item in categories] == ["5", "N"]
    assert categories[0].categoryName == "Category 5"
    assert categories[0].folder_name == "Category_5"
    assert categories[0].url.endswith("/cat5!messages")
    assert categories[1].url.endswith("/catn!messages")

    generic = downloader.messages_from_clickables(
        [
            downloader.Clickable(
                0,
                "MT n90 Advice of Charges",
                "https://www2.swift.com/mystandards/#/mt/2026.November/n90/!content",
                "A",
                "",
                "",
            ),
            downloader.Clickable(1, "MT 590 Wrong Category", "https://x/590", "A", "", ""),
        ],
        category=categories[1],
        source_page="https://x/catn",
    )
    assert [item.messageType for item in generic] == ["MTN90"]


def test_message_discovery_filters_by_category_prefix() -> None:
    category = downloader.Category(
        "6", "Category 6", "2026.November", "https://x", "https://x/cat6", "Category 6"
    )
    messages = downloader.messages_from_clickables(
        [
            downloader.Clickable(
                0, "MT600 Commodity Trade Confirmation", "https://x/600", "A", "", ""
            ),
            downloader.Clickable(1, "MT541 Receive Against Payment", "https://x/541", "A", "", ""),
        ],
        category=category,
        source_page="https://x/cat6",
    )
    assert [item.messageType for item in messages] == ["MT600"]


def test_message_type_pattern_matches_spaced_and_category_n_labels() -> None:
    assert re_search(downloader.message_type_pattern("MT200"), "MT 200 Transfer")
    assert re_search(downloader.message_type_pattern("MT200"), "MT200 Transfer")
    assert re_search(downloader.message_type_pattern("MTN90"), "MT n90 Advice")
    assert not re_search(downloader.message_type_pattern("MT200"), "MT 201 Transfer")


def test_filters() -> None:
    category = downloader.Category(
        "5", "Securities", "2026.November", "https://x", "https://x/5", "Category 5 Securities"
    )
    message = downloader.MessageItem(
        "5",
        "Securities",
        "MT541",
        "Receive Against Payment",
        "2026.November",
        "https://x/5",
        "https://x/MT541",
    )
    assert downloader.category_filter_matches(category, "5")
    assert downloader.category_filter_matches(category, "Securities")
    assert not downloader.category_filter_matches(category, "4")
    assert downloader.message_filter_matches(message, "mt541")
    assert not downloader.message_filter_matches(message, "MT540")
    assert message.folder_name == "Category_5_Securities"


def test_manifest_atomic_update_and_resume_skip(tmp_path: Path) -> None:
    store = downloader.ManifestStore(tmp_path, "2026.November")
    doc = tmp_path / "Category_5_Securities" / "SR_2026_November_MT541.pdf"
    doc.parent.mkdir()
    doc.write_bytes(b"%PDF-1.4\nMT541 Standards MT November 2026")
    sha = downloader.sha256_file(doc)
    entry = downloader.ManifestEntry(
        category="5",
        categoryName="Securities",
        messageType="MT541",
        messageName="Receive Against Payment",
        release="2026.November",
        sourcePage="https://x",
        documentType="PDF",
        originalFilename="server.pdf",
        savedFilename=doc.name,
        relativePath=str(doc.relative_to(tmp_path)),
        fileSize=doc.stat().st_size,
        sha256=sha,
        downloadedAt=downloader.now_iso(),
        status=downloader.DownloadStatus.SUCCESS.value,
        attempts=1,
    )
    store.upsert(entry)
    loaded = downloader.ManifestStore(tmp_path, "2026.November")
    message = downloader.MessageItem(
        "5",
        "Securities",
        "MT541",
        "Receive Against Payment",
        "2026.November",
        "https://x",
        "https://x",
    )
    assert loaded.find("5", "MT541", "PRIMARY") is None
    assert loaded.find_message("5", "MT541") is not None
    assert loaded.should_skip(message, force=False) is not None
    assert (tmp_path / "manifest.csv").exists()
    assert (tmp_path / "failures.json").exists()


def test_pdf_validation_detects_success_and_mismatches(tmp_path: Path) -> None:
    ok = tmp_path / "ok.pdf"
    ok.write_bytes(b"%PDF-1.4\nMT541 Receive Against Payment Standards MT November 2026")
    result = downloader.verify_download(ok, expected_message="MT541", release="2026.November")
    assert result.status == downloader.DownloadStatus.SUCCESS
    assert result.messageVerified is True
    assert result.releaseVerified is True

    wrong_message = tmp_path / "wrong-message.pdf"
    wrong_message.write_bytes(b"%PDF-1.4\nMT540 Receive Free Standards MT November 2026")
    result = downloader.verify_download(
        wrong_message, expected_message="MT541", release="2026.November"
    )
    assert result.status == downloader.DownloadStatus.MESSAGE_IDENTITY_MISMATCH

    wrong_release = tmp_path / "wrong-release.pdf"
    wrong_release.write_bytes(b"%PDF-1.4\nMT541 Receive Against Payment Standards MT November 2025")
    result = downloader.verify_download(
        wrong_release, expected_message="MT541", release="2026.November"
    )
    assert result.status == downloader.DownloadStatus.RELEASE_MISMATCH


def test_pdf_validation_rejects_login_html(tmp_path: Path) -> None:
    html = tmp_path / "login.pdf"
    html.write_bytes(b"<html><body>login required</body></html>")
    result = downloader.verify_download(html, expected_message="MT541", release="2026.November")
    assert result.status == downloader.DownloadStatus.FAILED
    assert "HTML/login" in result.error


def test_retry_retries_until_success() -> None:
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            raise RuntimeError("transient")
        return "ok"

    assert downloader.retry(operation, attempts=3, label="unit", backoff_seconds=0) == "ok"
    assert calls["count"] == 2
