#!/usr/bin/env python3
"""Headed SWIFT MyStandards MT Message Reference Guide downloader.

This is an operator utility. It uses the authenticated browser UI as the source of truth,
keeps MFA manual, downloads sequentially, and writes resumable manifests under Downloads.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_RELEASE = "2026.November"
TARGET_URL = "https://www2.swift.com/mystandards/#/mtcategories/mt/{release}"
DEFAULT_OUTPUT_NAME = "SWIFT_MT_2026_November"
EMAIL_ENV = "SWIFT_MYSTANDARDS_EMAIL"
PASSWORD_ENV = "SWIFT_MYSTANDARDS_PASSWORD"
EMAIL_ALIASES = (EMAIL_ENV, "SWIFT_EMAIL")
PASSWORD_ALIASES = (PASSWORD_ENV, "SWIFT_PASSWORD")

NAVIGATION_TIMEOUT_MS = 60_000
DOWNLOAD_START_TIMEOUT_MS = 60_000
DOWNLOAD_VERIFY_BYTES = 2_000_000
MAX_ATTEMPTS = 3
EXPORT_TARGET_ATTR = "data-swift-export-target"

LOGGER = logging.getLogger("swift_mystandards_downloader")


class DownloaderError(RuntimeError):
    """Base class for downloader failures."""


class ConfigurationError(DownloaderError):
    """Configuration is missing or invalid."""


class AuthState(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    LOGIN = "LOGIN"
    MFA = "MFA"
    CAPTCHA = "CAPTCHA"
    UNKNOWN = "UNKNOWN"


class DownloadStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED_VERIFIED = "SKIPPED_VERIFIED"
    FAILED = "FAILED"
    DOWNLOADED_UNVERIFIED = "DOWNLOADED_UNVERIFIED"
    RELEASE_MISMATCH = "RELEASE_MISMATCH"
    MESSAGE_IDENTITY_MISMATCH = "MESSAGE_IDENTITY_MISMATCH"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True)
class Config:
    release: str
    output: Path
    env_file: Path
    email: str
    password: str
    force: bool
    retry_failed: bool
    category: str | None
    message: str | None
    dry_run: bool
    keep_session: bool
    manual_login: bool
    attempts: int = MAX_ATTEMPTS


@dataclass(frozen=True, slots=True)
class Clickable:
    index: int
    text: str
    href: str
    tag: str
    role: str
    aria_label: str

    @property
    def label(self) -> str:
        return normalise_space(self.aria_label or self.text or self.href)


@dataclass(slots=True)
class Category:
    category: str
    categoryName: str
    release: str
    sourcePage: str
    url: str
    label: str

    @property
    def folder_name(self) -> str:
        if self.categoryName.lower() == f"category {self.category}".lower():
            return sanitize_filename(f"Category_{self.category}").strip("_")
        return sanitize_filename(f"Category_{self.category}_{self.categoryName}").strip("_")


@dataclass(slots=True)
class MessageItem:
    category: str
    categoryName: str
    messageType: str
    messageName: str
    release: str
    sourcePage: str
    url: str

    @property
    def folder_name(self) -> str:
        if self.categoryName.lower() == f"category {self.category}".lower():
            return sanitize_filename(f"Category_{self.category}").strip("_")
        return sanitize_filename(f"Category_{self.category}_{self.categoryName}").strip("_")


@dataclass(slots=True)
class VerificationResult:
    status: DownloadStatus
    fileSize: int
    sha256: str
    error: str = ""
    documentType: str = "UNKNOWN"
    releaseVerified: bool | None = None
    messageVerified: bool | None = None


@dataclass(slots=True)
class ManifestEntry:
    category: str
    categoryName: str
    messageType: str
    messageName: str
    release: str
    sourcePage: str
    documentType: str
    originalFilename: str
    savedFilename: str
    relativePath: str
    fileSize: int
    sha256: str
    downloadedAt: str
    status: str
    attempts: int
    error: str = ""
    duplicateOf: str = ""
    releaseVerified: bool | None = None
    messageVerified: bool | None = None

    @property
    def key(self) -> str:
        return manifest_key(self.category, self.messageType, self.documentType)


@dataclass(slots=True)
class RunStats:
    runStarted: str
    runCompleted: str = ""
    release: str = DEFAULT_RELEASE
    targetUrl: str = ""
    categoriesDiscovered: int = 0
    categoriesProcessed: int = 0
    messagesDiscovered: int = 0
    documentsDownloaded: int = 0
    alreadyExistingVerified: int = 0
    failures: int = 0
    duplicates: int = 0
    unverifiedDownloads: int = 0
    totalBytes: int = 0


class ManifestStore:
    def __init__(self, output: Path, release: str) -> None:
        self.output = output
        self.release = release
        self.manifest_path = output / "manifest.json"
        self.csv_path = output / "manifest.csv"
        self.failures_path = output / "failures.json"
        self.items: dict[str, ManifestEntry] = {}
        self.load()

    def load(self) -> None:
        if not self.manifest_path.exists():
            return
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("items", [])
        for row in rows:
            entry = ManifestEntry(**row)
            self.items[entry.key] = entry

    def find(
        self, category: str, message_type: str, document_type: str = "PRIMARY"
    ) -> ManifestEntry | None:
        return self.items.get(manifest_key(category, message_type, document_type))

    def find_message(self, category: str, message_type: str) -> ManifestEntry | None:
        primary = self.find(category, message_type)
        if primary is not None:
            return primary
        for item in sorted(self.items.values(), key=entry_sort_key):
            if item.category == category and item.messageType.upper() == message_type.upper():
                return item
        return None

    def find_verified_duplicate(self, sha256: str) -> ManifestEntry | None:
        for item in self.items.values():
            if item.sha256 == sha256 and item.status in {
                DownloadStatus.SUCCESS.value,
                DownloadStatus.SKIPPED_VERIFIED.value,
            }:
                return item
        return None

    def should_skip(self, message: MessageItem, *, force: bool) -> ManifestEntry | None:
        if force:
            return None
        entry = self.find_message(message.category, message.messageType)
        if entry is None:
            return None
        if entry.status not in {
            DownloadStatus.SUCCESS.value,
            DownloadStatus.SKIPPED_VERIFIED.value,
        }:
            return None
        path = self.output / entry.relativePath
        if not path.exists() or not path.is_file():
            return None
        if sha256_file(path) != entry.sha256:
            return None
        return entry

    def upsert(self, entry: ManifestEntry) -> None:
        self.items[entry.key] = entry
        self.write()

    def remove(self, category: str, message_type: str, document_type: str) -> None:
        key = manifest_key(category, message_type, document_type)
        if key in self.items:
            del self.items[key]
            self.write()

    def write(self) -> None:
        payload = {
            "release": self.release,
            "targetUrl": TARGET_URL.format(release=self.release),
            "updatedAt": now_iso(),
            "items": [asdict(item) for item in sorted(self.items.values(), key=entry_sort_key)],
        }
        atomic_write_text(self.manifest_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        self.write_csv()
        failures = [
            asdict(item)
            for item in sorted(self.items.values(), key=entry_sort_key)
            if item.status == DownloadStatus.FAILED.value
        ]
        atomic_write_text(self.failures_path, json.dumps(failures, indent=2, sort_keys=True) + "\n")

    def write_csv(self) -> None:
        fieldnames = list(ManifestEntry.__dataclass_fields__.keys())
        tmp = tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(self.output), encoding="utf-8", newline=""
        )
        try:
            with tmp:
                writer = csv.DictWriter(tmp, fieldnames=fieldnames)
                writer.writeheader()
                for item in sorted(self.items.values(), key=entry_sort_key):
                    writer.writerow(asdict(item))
            Path(tmp.name).replace(self.csv_path)
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise


def entry_sort_key(entry: ManifestEntry) -> tuple[str, str, str]:
    return (entry.category, entry.messageType, entry.documentType)


def manifest_key(category: str, message_type: str, document_type: str = "PRIMARY") -> str:
    return f"{category}::{message_type.upper()}::{document_type.upper()}"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def default_output_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Downloads" / DEFAULT_OUTPUT_NAME


def normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def sanitize_filename(value: str, *, default: str = "document") -> str:
    normalised = unicodedata.normalize("NFKD", value)
    ascii_value = normalised.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r'[\/\\:*?"<>|]+', "_", ascii_value)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    cleaned = re.sub(r"_+(\.[A-Za-z0-9]+)$", r"\1", cleaned)
    return cleaned or default


def release_slug(release: str) -> str:
    return sanitize_filename(release.replace(".", "_"))


def category_filter_matches(category: Category, wanted: str | None) -> bool:
    if wanted is None:
        return True
    target = wanted.strip().lower()
    return target in {
        category.category.lower(),
        f"category {category.category}".lower(),
        f"category_{category.category}".lower(),
        category.categoryName.lower(),
        category.label.lower(),
    }


def message_filter_matches(message: MessageItem, wanted: str | None) -> bool:
    if wanted is None:
        return True
    return message.messageType.upper() == wanted.strip().upper()


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_config(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description="Download SWIFT MT 2026.November MyStandards documents."
    )
    parser.add_argument("--release", default=DEFAULT_RELEASE)
    parser.add_argument("--output", type=Path, default=default_output_dir())
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--category")
    parser.add_argument("--message")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-session", action="store_true")
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Skip first-factor autofill and wait for manual login/MFA.",
    )
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS)
    args = parser.parse_args(argv)

    env_file_values = read_env_file(args.env_file.expanduser())
    merged = {**env_file_values, **os.environ}
    email = first_configured(merged, EMAIL_ALIASES).strip()
    password = first_configured(merged, PASSWORD_ALIASES)
    missing: list[str] = []
    if not email:
        missing.append(f"{EMAIL_ENV} is not configured.")
    if not password:
        missing.append(f"{PASSWORD_ENV} is not configured.")
    if missing:
        raise ConfigurationError("\n".join(missing))

    return Config(
        release=args.release,
        output=args.output.expanduser(),
        env_file=args.env_file.expanduser(),
        email=email,
        password=password,
        force=args.force,
        retry_failed=args.retry_failed,
        category=args.category,
        message=args.message.upper() if args.message else None,
        dry_run=args.dry_run,
        keep_session=args.keep_session,
        manual_login=args.manual_login,
        attempts=max(1, args.attempts),
    )


def first_configured(values: dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = values.get(name, "")
        if value:
            return value
    return ""


def ensure_output_tree(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "debug").mkdir(exist_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_head(path: Path, limit: int = DOWNLOAD_VERIFY_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)


def extract_pdf_text(path: Path, fallback_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:
        return fallback_bytes.decode("latin-1", errors="ignore")

    try:
        reader = PdfReader(str(path))
        texts: list[str] = []
        for page in reader.pages[:5]:
            texts.append(page.extract_text() or "")
        return "\n".join(texts) or fallback_bytes.decode("latin-1", errors="ignore")
    except Exception as exc:
        LOGGER.info("PDF text extraction failed for %s: %s", path.name, exc)
        return ""


def verify_download(path: Path, *, expected_message: str, release: str) -> VerificationResult:
    if not path.exists() or not path.is_file():
        return VerificationResult(DownloadStatus.FAILED, 0, "", "Downloaded file does not exist.")
    size = path.stat().st_size
    if size <= 0:
        return VerificationResult(DownloadStatus.FAILED, size, "", "Downloaded file is empty.")
    sha = sha256_file(path)
    head = read_head(path)
    lower_head = head[:4096].lower().lstrip()
    extension = path.suffix.lower()

    if (
        lower_head.startswith(b"<!doctype html")
        or lower_head.startswith(b"<html")
        or b"login" in lower_head
    ):
        return VerificationResult(
            DownloadStatus.FAILED,
            size,
            sha,
            "Downloaded content looks like an HTML/login page, not a standards document.",
            documentType="HTML",
        )

    if extension == ".pdf" or head.startswith(b"%PDF"):
        if not head.startswith(b"%PDF"):
            return VerificationResult(
                DownloadStatus.FAILED,
                size,
                sha,
                "PDF file does not start with %PDF.",
                "PDF",
            )
        text = normalise_space(extract_pdf_text(path, head))
        if not text:
            return VerificationResult(
                DownloadStatus.DOWNLOADED_UNVERIFIED,
                size,
                sha,
                "PDF is structurally present, but text extraction was not available.",
                "PDF",
            )
        expected = expected_message.upper().replace(" ", "")
        compact_text = text.upper().replace(" ", "")
        message_verified = expected in compact_text
        release_verified = release_matches_text(release, text)
        if not message_verified:
            return VerificationResult(
                DownloadStatus.MESSAGE_IDENTITY_MISMATCH,
                size,
                sha,
                f"PDF text did not contain expected message identity {expected_message}.",
                "PDF",
                releaseVerified=release_verified,
                messageVerified=False,
            )
        if release_verified is False:
            return VerificationResult(
                DownloadStatus.RELEASE_MISMATCH,
                size,
                sha,
                f"PDF text did not match expected release {release}.",
                "PDF",
                releaseVerified=False,
                messageVerified=True,
            )
        if release_verified is None:
            return VerificationResult(
                DownloadStatus.DOWNLOADED_UNVERIFIED,
                size,
                sha,
                "PDF message identity matched, but release identity could not be verified.",
                "PDF",
                releaseVerified=None,
                messageVerified=True,
            )
        return VerificationResult(
            DownloadStatus.SUCCESS,
            size,
            sha,
            documentType="PDF",
            releaseVerified=True,
            messageVerified=True,
        )

    if extension == ".zip" or head.startswith(b"PK\x03\x04"):
        return VerificationResult(DownloadStatus.SUCCESS, size, sha, documentType="ZIP")

    return VerificationResult(
        DownloadStatus.DOWNLOADED_UNVERIFIED,
        size,
        sha,
        f"Downloaded file type {extension or 'without extension'} was not recognised.",
    )


def release_matches_text(release: str, text: str) -> bool | None:
    lower = text.lower()
    year_match = re.search(r"(20\d{2})", release)
    year = year_match.group(1) if year_match else ""
    month = "november" if "november" in release.lower() else ""
    wrong_year = "2025" if year == "2026" else ""
    if wrong_year and wrong_year in lower and year not in lower:
        return False
    if year and year in lower and (not month or month in lower):
        return True
    if "standards mt" in lower and month and month not in lower:
        return False
    return None


def classify_auth_state_text(
    url: str, text: str, *, has_password_field: bool, release: str
) -> AuthState:
    lower = text.lower()
    url_lower = url.lower()
    if "captcha" in lower or "captcha" in url_lower:
        return AuthState.CAPTCHA
    if any(
        token in lower
        for token in (
            "two-step",
            "two step",
            "multi-factor",
            "mfa",
            "verification code",
            "one-time",
            "otp",
            "authenticator",
        )
    ):
        return AuthState.MFA
    if has_password_field or (
        "password" in lower and any(token in lower for token in ("sign in", "login", "log in"))
    ):
        return AuthState.LOGIN
    if "login" in url_lower or "signin" in url_lower or "sso" in url_lower:
        return AuthState.LOGIN
    release_route = release.lower()
    if "mystandards" in url_lower and (
        f"/mt/{release_route}/" in url_lower
        or f"/mtcategories/mt/{release_route}" in url_lower
    ):
        return AuthState.AUTHENTICATED
    if "mystandards" in url_lower and (
        "mtcategories" in url_lower
        or release.lower() in lower
        or "category" in lower
        or "message" in lower
    ):
        return AuthState.AUTHENTICATED
    return AuthState.UNKNOWN


def retry(
    operation: Callable[[], Any], *, attempts: int, label: str, backoff_seconds: float = 1.0
) -> Any:
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last = exc
            if attempt >= attempts:
                break
            sleep_for = backoff_seconds * attempt
            LOGGER.warning(
                "%s failed on attempt %s/%s; retrying in %.1fs: %s",
                label,
                attempt,
                attempts,
                sleep_for,
                exc,
            )
            time.sleep(sleep_for)
    assert last is not None
    raise last


class MyStandardsDownloader:
    def __init__(self, config: Config) -> None:
        self.config = config
        ensure_output_tree(config.output)
        self.manifest = ManifestStore(config.output, config.release)
        self.stats = RunStats(
            runStarted=now_iso(), release=config.release, targetUrl=self.target_url
        )

    @property
    def target_url(self) -> str:
        return TARGET_URL.format(release=self.config.release)

    def run(self) -> int:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ConfigurationError(
                "Python Playwright is not installed. Run "
                "`pip install -r backend/requirements-dev.txt` and "
                "`python -m playwright install chromium`."
            ) from exc

        with sync_playwright() as playwright:
            context = None
            browser = None
            try:
                if self.config.keep_session:
                    profile = self.config.output / ".browser-profile"
                    context = playwright.chromium.launch_persistent_context(
                        str(profile),
                        headless=False,
                        accept_downloads=True,
                        viewport={"width": 1440, "height": 1000},
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                else:
                    browser = playwright.chromium.launch(headless=False)
                    context = browser.new_context(
                        accept_downloads=True, viewport={"width": 1440, "height": 1000}
                    )
                    page = context.new_page()

                self.authenticate(page)
                categories = self.discover_categories(page)
                categories = [
                    item
                    for item in categories
                    if category_filter_matches(item, self.config.category)
                ]
                self.stats.categoriesDiscovered = len(categories)
                all_messages: list[MessageItem] = []
                for category in categories:
                    (self.config.output / category.folder_name).mkdir(parents=True, exist_ok=True)
                    try:
                        messages = self.discover_messages(page, category)
                        messages = [
                            item
                            for item in messages
                            if message_filter_matches(item, self.config.message)
                        ]
                        all_messages.extend(messages)
                        self.stats.categoriesProcessed += 1
                    except Exception as exc:
                        self.record_category_failure(category, exc)
                        continue

                self.stats.messagesDiscovered = len(all_messages)
                if self.config.dry_run:
                    self.print_dry_run(categories, all_messages)
                    self.stats.runCompleted = now_iso()
                    self.write_report(categories, all_messages)
                    return 0

                for message in all_messages:
                    if self.config.retry_failed:
                        previous = self.manifest.find_message(message.category, message.messageType)
                        if previous is None or previous.status != DownloadStatus.FAILED.value:
                            continue
                    self.process_message(page, message, PlaywrightTimeoutError)

                self.stats.runCompleted = now_iso()
                self.recalculate_stats()
                self.write_report(categories, all_messages)
                return 0 if self.stats.failures == 0 else 2
            finally:
                if not self.config.keep_session:
                    if context is not None:
                        close_quietly(context)
                    if browser is not None:
                        close_quietly(browser)

    def authenticate(self, page: Any) -> None:
        self.goto(page, self.target_url)
        if self.verify_authenticated(page):
            return
        if not self.config.manual_login:
            if self.try_first_factor_login(page) and self.verify_authenticated(page):
                return
        self.wait_for_manual_auth(page)

    def try_first_factor_login(self, page: Any) -> bool:
        LOGGER.info("Attempting first-factor login with configured MyStandards credentials.")
        email = first_visible(
            page,
            [
                lambda: page.get_by_label(re.compile("email|e-mail|user|username", re.I)),
                lambda: page.locator("input[type='email']"),
                lambda: page.locator("input[name*='email' i]"),
                lambda: page.locator("input[name*='user' i]"),
                lambda: page.locator("input[id*='email' i]"),
                lambda: page.locator("input[id*='user' i]"),
            ],
        )
        if email is None:
            LOGGER.info("No safe email/username field was found; falling back to manual login.")
            return False
        email.fill(self.config.email)
        click_first_visible(
            page,
            [
                lambda: page.get_by_role("button", name=re.compile("next|continue", re.I)),
                lambda: page.get_by_role("button", name=re.compile("sign in|log in|login", re.I)),
            ],
            timeout_ms=2_000,
        )
        wait_soft(page, 2_000)

        password = first_visible(
            page,
            [
                lambda: page.get_by_label(re.compile("password", re.I)),
                lambda: page.locator("input[type='password']"),
                lambda: page.locator("input[name*='password' i]"),
                lambda: page.locator("input[id*='password' i]"),
            ],
        )
        if password is None:
            LOGGER.info(
                "No safe password field was found after username step; "
                "falling back to manual login."
            )
            return False
        password.fill(self.config.password)
        submitted = click_first_visible(
            page,
            [
                lambda: page.get_by_role(
                    "button", name=re.compile("sign in|log in|login|continue|submit", re.I)
                ),
                lambda: page.locator("button[type='submit']"),
                lambda: page.locator("input[type='submit']"),
            ],
            timeout_ms=5_000,
        )
        if not submitted:
            password.press("Enter")
        wait_soft(page, 5_000)
        state = self.classify_auth_state(page)
        if state in {AuthState.MFA, AuthState.CAPTCHA}:
            return False
        if state == AuthState.LOGIN:
            raise DownloaderError(
                "SWIFT login did not complete. Check the configured email/password."
            )
        return state == AuthState.AUTHENTICATED

    def wait_for_manual_auth(self, page: Any) -> None:
        while True:
            print(
                "\n================================================================\n"
                "SWIFT TWO-STEP VERIFICATION REQUIRED\n\n"
                "Complete the verification manually in the browser.\n\n"
                "After MyStandards has finished loading, return to this terminal\n"
                "and press ENTER to continue.\n"
                "================================================================\n",
                flush=True,
            )
            input()
            if self.verify_authenticated(page):
                return
            print(
                "Authentication is still incomplete. Complete SWIFT login/two-step verification "
                "in the same browser, then press ENTER again.",
                flush=True,
            )

    def verify_authenticated(self, page: Any) -> bool:
        self.goto(page, self.target_url)
        state = self.classify_auth_state(page)
        return state == AuthState.AUTHENTICATED

    def classify_auth_state(self, page: Any) -> AuthState:
        try:
            text = page.locator("body").inner_text(timeout=5_000)
        except Exception:
            text = ""
        try:
            has_password = page.locator("input[type='password']").count() > 0
        except Exception:
            has_password = False
        return classify_auth_state_text(
            page.url, text, has_password_field=has_password, release=self.config.release
        )

    def goto(self, page: Any, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        wait_soft(page, 1_000)

    def discover_categories(self, page: Any) -> list[Category]:
        self.goto(page, self.target_url)
        clickables = collect_clickables(page)
        categories = categories_from_clickables(
            clickables, release=self.config.release, source_page=page.url
        )
        if not categories:
            self.write_discovery_debug("category-discovery.json", clickables, page.url)
            raise DownloaderError(
                "No MT categories were discovered from the authenticated MyStandards catalogue."
            )
        LOGGER.info("Discovered %s categories.", len(categories))
        return categories

    def discover_messages(self, page: Any, category: Category) -> list[MessageItem]:
        self.goto(page, self.target_url)
        clicked = click_by_visible_text(page, category.label)
        if not clicked:
            clicked = click_by_visible_text(page, f"Category {category.category}")
        if not clicked:
            raise DownloaderError(f"Could not open category {category.label}.")
        wait_for_category(page, category)
        clickables = collect_clickables(page)
        messages = messages_from_clickables(clickables, category=category, source_page=page.url)
        if not messages:
            self.write_discovery_debug(
                f"message-discovery-{category.category}.json", clickables, page.url
            )
            raise DownloaderError(f"No MT messages were discovered for category {category.label}.")
        self.manifest.remove(category.category, "CATEGORY", "CATEGORY_DISCOVERY")
        LOGGER.info("Category %s: discovered %s messages.", category.label, len(messages))
        return messages

    def process_message(
        self, page: Any, message: MessageItem, timeout_error_type: type[BaseException]
    ) -> None:
        previous = self.manifest.should_skip(message, force=self.config.force)
        if previous is not None:
            skipped = ManifestEntry(
                **{
                    **asdict(previous),
                    "status": DownloadStatus.SKIPPED_VERIFIED.value,
                    "downloadedAt": now_iso(),
                }
            )
            self.manifest.upsert(skipped)
            print(f"[SKIP] {message.messageType} already downloaded and verified.")
            return

        attempts = 0
        try:
            def operation() -> ManifestEntry:
                nonlocal attempts
                attempts += 1
                return self.download_one(page, message, attempts, timeout_error_type)

            entry = retry(operation, attempts=self.config.attempts, label=message.messageType)
            self.manifest.upsert(entry)
            if entry.status == DownloadStatus.SUCCESS.value:
                print(f"[OK] {message.messageType} -> {entry.relativePath}")
            else:
                print(f"[WARN] {message.messageType} -> {entry.status}: {entry.error}")
        except Exception as exc:
            entry = self.failure_entry(message, attempts or 1, "DOWNLOAD", exc)
            self.manifest.upsert(entry)
            print(f"[FAIL] {message.messageType}: {exc}")

    def download_one(
        self,
        page: Any,
        message: MessageItem,
        attempts: int,
        timeout_error_type: type[BaseException],
    ) -> ManifestEntry:
        self.open_message_page(page, message)
        if self.classify_auth_state(page) != AuthState.AUTHENTICATED:
            print(
                "SWIFT session expired. Re-authenticate in the browser and press ENTER.",
                flush=True,
            )
            self.wait_for_manual_auth(page)
            self.open_message_page(page, message)
        clickables = collect_clickables(page)
        self.write_discovery_debug(
            f"download-page-{message.messageType}.json", clickables, page.url, page=page
        )
        try:
            download = export_plain_pdf_download(page, timeout_error_type)
            return self.save_and_verify_download(download, message, attempts)
        except Exception as exc:
            self.write_discovery_debug(
                f"export-failure-{message.messageType}.json",
                collect_clickables(page),
                page.url,
                page=page,
            )
            raise DownloaderError(
                f"Export -> PDF -> Plain PDF flow failed for {message.messageType}: {exc}"
            ) from exc

    def open_message_page(self, page: Any, message: MessageItem) -> None:
        self.goto(page, self.target_url)
        if click_by_visible_text(page, f"Category {message.category}"):
            wait_for_category(
                page,
                Category(
                    category=message.category,
                    categoryName=message.categoryName,
                    release=message.release,
                    sourcePage=self.target_url,
                    url=category_route(self.target_url, message.release, message.category),
                    label=f"Category {message.category}",
                ),
            )
            if click_message_link(page, message):
                wait_for_message_page(page, message)
                return

        if message.url:
            self.goto(page, message.url)
            wait_for_message_page(page, message)
            return

        raise DownloaderError(f"Could not open message {message.messageType}.")

    def save_and_verify_download(
        self, download: Any, message: MessageItem, attempts: int
    ) -> ManifestEntry:
        original_name = download.suggested_filename or f"{message.messageType}.pdf"
        extension = safe_extension(original_name)
        category_dir = self.config.output / message.folder_name
        category_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            sanitize_filename(
                f"SR_{release_slug(message.release)}_{message.messageType}_{message.messageName}",
                default=message.messageType,
            )
            + extension
        )
        target = unique_path(category_dir / filename)
        download.save_as(str(target))
        verification = verify_download(
            target, expected_message=message.messageType, release=message.release
        )
        duplicate_of = ""
        final_status = verification.status
        duplicate = (
            self.manifest.find_verified_duplicate(verification.sha256)
            if verification.sha256
            else None
        )
        if duplicate is not None and duplicate.relativePath != str(
            target.relative_to(self.config.output)
        ):
            duplicate_of = duplicate.relativePath
            target.unlink(missing_ok=True)
            target = self.config.output / duplicate.relativePath
            filename = target.name
            final_status = DownloadStatus.DUPLICATE
        return ManifestEntry(
            category=message.category,
            categoryName=message.categoryName,
            messageType=message.messageType,
            messageName=message.messageName,
            release=message.release,
            sourcePage=message.sourcePage,
            documentType=(
                verification.documentType
                if verification.documentType != "UNKNOWN"
                else "PRIMARY"
            ),
            originalFilename=original_name,
            savedFilename=filename,
            relativePath=str(target.relative_to(self.config.output)),
            fileSize=verification.fileSize,
            sha256=verification.sha256,
            downloadedAt=now_iso(),
            status=final_status.value,
            attempts=attempts,
            error=verification.error,
            duplicateOf=duplicate_of,
            releaseVerified=verification.releaseVerified,
            messageVerified=verification.messageVerified,
        )

    def record_category_failure(self, category: Category, exc: Exception) -> None:
        entry = ManifestEntry(
            category=category.category,
            categoryName=category.categoryName,
            messageType="CATEGORY",
            messageName=category.label,
            release=category.release,
            sourcePage=category.sourcePage,
            documentType="CATEGORY_DISCOVERY",
            originalFilename="",
            savedFilename="",
            relativePath="",
            fileSize=0,
            sha256="",
            downloadedAt=now_iso(),
            status=DownloadStatus.FAILED.value,
            attempts=1,
            error=str(exc),
        )
        self.manifest.upsert(entry)

    def failure_entry(
        self, message: MessageItem, attempts: int, stage: str, exc: Exception
    ) -> ManifestEntry:
        return ManifestEntry(
            category=message.category,
            categoryName=message.categoryName,
            messageType=message.messageType,
            messageName=message.messageName,
            release=message.release,
            sourcePage=message.sourcePage,
            documentType="PRIMARY",
            originalFilename="",
            savedFilename="",
            relativePath="",
            fileSize=0,
            sha256="",
            downloadedAt=now_iso(),
            status=DownloadStatus.FAILED.value,
            attempts=attempts,
            error=f"{stage}: {exc}",
        )

    def recalculate_stats(self) -> None:
        items = list(self.manifest.items.values())
        self.stats.documentsDownloaded = sum(
            1 for item in items if item.status == DownloadStatus.SUCCESS.value
        )
        self.stats.alreadyExistingVerified = sum(
            1 for item in items if item.status == DownloadStatus.SKIPPED_VERIFIED.value
        )
        self.stats.failures = sum(1 for item in items if item.status == DownloadStatus.FAILED.value)
        self.stats.duplicates = sum(
            1 for item in items if item.status == DownloadStatus.DUPLICATE.value
        )
        self.stats.unverifiedDownloads = sum(
            1 for item in items if item.status == DownloadStatus.DOWNLOADED_UNVERIFIED.value
        )
        self.stats.totalBytes = sum(item.fileSize for item in items if item.fileSize > 0)

    def write_report(self, categories: list[Category], messages: list[MessageItem]) -> None:
        self.recalculate_stats()
        by_category: dict[str, list[MessageItem]] = {}
        for message in messages:
            by_category.setdefault(message.category, []).append(message)
        lines = [
            "# SWIFT MT MyStandards Download Report",
            "",
            f"SWIFT MT release: `{self.config.release}`",
            f"Run started: `{self.stats.runStarted}`",
            f"Run completed: `{self.stats.runCompleted or now_iso()}`",
            f"Categories discovered: `{len(categories)}`",
            f"Categories processed: `{self.stats.categoriesProcessed}`",
            f"Messages discovered: `{len(messages)}`",
            f"Documents downloaded: `{self.stats.documentsDownloaded}`",
            f"Already existing verified: `{self.stats.alreadyExistingVerified}`",
            f"Failures: `{self.stats.failures}`",
            f"Duplicate documents: `{self.stats.duplicates}`",
            f"Unverified downloads: `{self.stats.unverifiedDownloads}`",
            f"Total bytes: `{self.stats.totalBytes}`",
            f"Output directory: `{self.config.output}`",
            "",
            "## Categories",
        ]
        for category in categories:
            lines.extend(["", f"### Category {category.category} {category.categoryName}".rstrip()])
            for message in sorted(
                by_category.get(category.category, []), key=lambda item: item.messageType
            ):
                entry = self.manifest.find_message(message.category, message.messageType)
                status = (
                    entry.status
                    if entry
                    else ("DISCOVERED" if self.config.dry_run else "PENDING")
                )
                lines.append(f"- `{message.messageType}` - {status}")
        atomic_write_text(self.config.output / "download-report.md", "\n".join(lines) + "\n")

    def print_dry_run(self, categories: list[Category], messages: list[MessageItem]) -> None:
        print(f"Categories discovered: {len(categories)}")
        print(f"Messages discovered: {len(messages)}")
        grouped: dict[str, list[MessageItem]] = {}
        for message in messages:
            grouped.setdefault(message.category, []).append(message)
        for category in categories:
            print(f"Category {category.category}: {category.categoryName}")
            for message in sorted(
                grouped.get(category.category, []), key=lambda item: item.messageType
            ):
                print(f"  {message.messageType} - {message.messageName}")

    def write_discovery_debug(
        self, filename: str, clickables: list[Clickable], url: str, *, page: Any | None = None
    ) -> None:
        body_text = ""
        if page is not None:
            try:
                body_text = page.locator("body").inner_text(timeout=2_000)
            except Exception:
                body_text = ""
        payload = {
            "url": url,
            "capturedAt": now_iso(),
            "bodyTextPreview": normalise_space(body_text)[:10_000],
            "clickables": [asdict(item) for item in clickables],
        }
        atomic_write_text(
            self.config.output / "debug" / filename,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )


def first_visible(
    page: Any, factories: Iterable[Callable[[], Any]], *, timeout_ms: int = 2_000
) -> Any | None:
    for factory in factories:
        try:
            locator = factory().first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception:
            continue
    return None


def click_first_visible(
    page: Any, factories: Iterable[Callable[[], Any]], *, timeout_ms: int = 2_000
) -> bool:
    locator = first_visible(page, factories, timeout_ms=timeout_ms)
    if locator is None:
        return False
    locator.click(timeout=timeout_ms)
    return True


def click_by_visible_text(page: Any, text: str) -> bool:
    try:
        page.get_by_text(text, exact=False).first.click(timeout=5_000)
        return True
    except Exception:
        return False


def click_message_link(page: Any, message: MessageItem) -> bool:
    pattern = re.compile(message_type_pattern(message.messageType), re.I)
    locator = first_visible(
        page,
        [
            lambda: page.get_by_role("link", name=pattern),
            lambda: page.get_by_role("button", name=pattern),
            lambda: page.locator("a", has_text=pattern),
            lambda: page.locator("[role='link']", has_text=pattern),
            lambda: page.locator("[role='button']", has_text=pattern),
            lambda: page.get_by_text(pattern),
        ],
        timeout_ms=5_000,
    )
    if locator is None:
        return False
    locator.click(timeout=10_000)
    return True


def message_type_pattern(message_type: str) -> str:
    suffix = re.escape(message_type.upper().removeprefix("MT"))
    return rf"\bMT\s*{suffix}\b"


def close_quietly(target: Any) -> None:
    try:
        target.close()
    except Exception:
        pass


def wait_soft(page: Any, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        page.wait_for_timeout(timeout_ms)
    except Exception:
        pass


def wait_for_category(page: Any, category: Category) -> None:
    fragment = f"cat{category.category.lower()}!messages"
    try:
        page.wait_for_url(re.compile(re.escape(fragment), re.I), timeout=10_000)
    except Exception:
        pass
    wait_soft(page, 2_000)


def wait_for_message_page(page: Any, message: MessageItem) -> None:
    try:
        page.wait_for_function(
            """
            ([messageType]) => {
              const text = document.body ? document.body.innerText : '';
              const normalized = text.toUpperCase();
              const compact = normalized.replace(/\\s+/g, '');
              const wantedCompact = messageType.toUpperCase();
              const wantedSpaced = wantedCompact.replace(/^MT/, 'MT ');
              return (compact.includes(wantedCompact) || normalized.includes(wantedSpaced))
                && /\\bExport\\b/i.test(text)
                && !/^\\s*Loading\\.\\.\\.\\s*$/i.test(text);
            }
            """,
            [message.messageType],
            timeout=45_000,
        )
    except Exception as exc:
        raise DownloaderError(
            f"Message page did not finish loading for {message.messageType}."
        ) from exc
    wait_soft(page, 2_000)


def collect_clickables(page: Any) -> list[Clickable]:
    raw = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a,button,[role="link"],[role="button"]'))
          .map((el, index) => {
            el.setAttribute('data-swift-downloader-index', String(index));
            return {
              index,
              text: (el.innerText || el.textContent || '').trim(),
              href: el.href || el.getAttribute('href') || '',
              tag: el.tagName || '',
              role: el.getAttribute('role') || '',
              aria_label: el.getAttribute('aria-label') || ''
            };
          });
        """
    )
    return [Clickable(**item) for item in raw]


def categories_from_clickables(
    clickables: list[Clickable], *, release: str, source_page: str
) -> list[Category]:
    categories: dict[str, Category] = {}
    release_lower = release.lower()
    for item in clickables:
        label = item.label
        haystack = f"{label} {item.href}".strip()
        lower = haystack.lower()
        if "mtcategories" not in lower and "category" not in lower:
            continue
        if release_lower not in lower and "category" not in lower:
            continue
        category_number = extract_category_number(haystack)
        if category_number is None:
            continue
        name = extract_category_name(label, category_number)
        if category_number not in categories:
            categories[category_number] = Category(
                category=category_number,
                categoryName=name,
                release=release,
                sourcePage=source_page,
                url=item.href or category_route(source_page, release, category_number),
                label=label,
            )
    return sorted(categories.values(), key=lambda item: natural_category_key(item.category))


def extract_category_number(value: str) -> str | None:
    patterns = [
        r"\bCategory\s*([0-9A-Za-z]+)\b",
        r"\bcat([0-9A-Za-z]+)!messages\b",
        r"\bcat(?:egory)?[=/_-]?([0-9A-Za-z]+)\b",
        r"/category/([0-9A-Za-z]+)\b",
        r"/mtcategories/mt/[^/#?]+/([0-9A-Za-z]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            raw = match.group(1).upper()
            if raw == "N" or raw.isdigit():
                return raw
    return None


def extract_category_name(label: str, category_number: str) -> str:
    text = normalise_space(label)
    text = re.sub(rf"\bCategory\s*{re.escape(category_number)}\b", "", text, flags=re.I)
    text = re.sub(r"\(\d+\)", "", text)
    text = re.sub(r"\bMT\b", "", text, flags=re.I)
    text = normalise_space(text.strip(" -:|"))
    return text or f"Category {category_number}"


def category_route(source_page: str, release: str, category_number: str) -> str:
    base = source_page.split("#", 1)[0]
    return f"{base}#/mtcategories/mt/{release}/cat{category_number.lower()}!messages"


def natural_category_key(value: str) -> tuple[int, str]:
    return (int(value), value) if value.isdigit() else (999, value)


def messages_from_clickables(
    clickables: list[Clickable], *, category: Category, source_page: str
) -> list[MessageItem]:
    messages: dict[str, MessageItem] = {}
    for item in clickables:
        label = item.label
        match = re.search(r"\bMT\s*([0-9]{3}|[Nn][0-9]{2})\b", label, re.I) or re.search(
            r"/mt/[^/]+/([0-9]{3}|[Nn][0-9]{2})/!content\b", item.href, re.I
        )
        if not match:
            continue
        message_suffix = match.group(1).upper()
        if not message_belongs_to_category(message_suffix, category.category):
            continue
        message_type = f"MT{message_suffix}".upper()
        name = extract_message_name(label, message_type)
        if message_type not in messages:
            messages[message_type] = MessageItem(
                category=category.category,
                categoryName=category.categoryName,
                messageType=message_type,
                messageName=name,
                release=category.release,
                sourcePage=source_page,
                url=item.href,
            )
    return sorted(messages.values(), key=lambda item: item.messageType)


def extract_message_name(label: str, message_type: str) -> str:
    text = normalise_space(label)
    text = re.sub(
        rf"\b{message_type[:2]}\s*{re.escape(message_type[2:])}\b",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(Message Reference Guide|MRG|Download|PDF|Document)\b", "", text, flags=re.I)
    text = normalise_space(text.strip(" -:|"))
    return text or message_type


def message_belongs_to_category(message_suffix: str, category_number: str) -> bool:
    category = category_number.upper()
    suffix = message_suffix.upper()
    if category == "N":
        return suffix.startswith("N")
    return suffix.startswith(category)


def rank_download_candidates(clickables: list[Clickable]) -> list[Clickable]:
    scored: list[tuple[int, Clickable]] = []
    for item in clickables:
        label = item.label
        lower = f"{label} {item.href}".lower()
        if is_global_navigation_candidate(lower):
            continue
        score = 0
        if "message reference guide" in lower or re.search(r"\bmrg\b", lower):
            score += 100
        if "standards" in lower or "reference" in lower:
            score += 50
        if "pdf" in lower:
            score += 40
        if "download" in lower:
            score += 30
        if "document" in lower or "guide" in lower:
            score += 20
        if score:
            scored.append((score, item))
    return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)]


def export_plain_pdf_download(page: Any, timeout_error_type: type[BaseException]) -> Any:
    export = first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile(r"\bexport\b", re.I)),
            lambda: page.get_by_role("link", name=re.compile(r"\bexport\b", re.I)),
            lambda: page.get_by_text(re.compile(r"^\s*export\s*$", re.I)),
            lambda: page.locator("[aria-label*='Export' i]"),
            lambda: page.locator("[title*='Export' i]"),
        ],
        timeout_ms=8_000,
    )
    if export is None:
        raise DownloaderError("Export control was not found on the message page.")
    export.click(timeout=10_000)
    wait_soft(page, 1_000)

    plain_pdf = find_plain_pdf_control(page, timeout_ms=1_000)
    if plain_pdf is None:
        pdf_menu = find_pdf_menu_control(page, timeout_ms=8_000)
        if pdf_menu is None:
            raise DownloaderError("PDF export control was not found after opening Export.")
        pdf_menu.click(timeout=10_000)
        wait_soft(page, 1_000)
        plain_pdf = find_plain_pdf_control(page, timeout_ms=10_000)
    if plain_pdf is None:
        raise DownloaderError("Plain PDF option was not found after opening Export.")
    try:
        with page.expect_download(timeout=DOWNLOAD_START_TIMEOUT_MS) as download_info:
            plain_pdf.click(timeout=10_000)
        return download_info.value
    except timeout_error_type as exc:
        raise DownloaderError("Plain PDF did not start a download within the timeout.") from exc


def find_plain_pdf_control(page: Any, *, timeout_ms: int) -> Any | None:
    locator = first_visible(
        page,
        [
            lambda: page.get_by_role("link", name=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.get_by_role("menuitem", name=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.get_by_role("button", name=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.locator("a", has_text=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.locator("button", has_text=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.locator("[role='menuitem']", has_text=re.compile(r"plain\s*pdf", re.I)),
            lambda: page.locator("[aria-label*='Plain PDF' i]"),
            lambda: page.locator("[title*='Plain PDF' i]"),
        ],
        timeout_ms=timeout_ms,
    )
    if locator is not None:
        return locator
    return find_marked_export_control(page, "plain-pdf", timeout_ms=timeout_ms)


def find_pdf_menu_control(page: Any, *, timeout_ms: int) -> Any | None:
    locator = first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile(r"^\s*pdf\s*$", re.I)),
            lambda: page.get_by_role("link", name=re.compile(r"^\s*pdf\s*$", re.I)),
            lambda: page.get_by_role("menuitem", name=re.compile(r"^\s*pdf\s*$", re.I)),
            lambda: page.locator("button", has_text=re.compile(r"^\s*PDF\s*$", re.I)),
            lambda: page.locator("a", has_text=re.compile(r"^\s*PDF\s*$", re.I)),
            lambda: page.locator("[role='menuitem']", has_text=re.compile(r"^\s*PDF\s*$", re.I)),
            lambda: page.locator("[aria-label*='PDF' i]"),
            lambda: page.locator("[title*='PDF' i]"),
        ],
        timeout_ms=timeout_ms,
    )
    if locator is not None:
        return locator
    return find_marked_export_control(page, "pdf-menu", timeout_ms=timeout_ms)


def find_marked_export_control(page: Any, marker: str, *, timeout_ms: int) -> Any | None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() <= deadline:
        if mark_export_controls(page, marker):
            locator = page.locator(f'[{EXPORT_TARGET_ATTR}="{marker}"]').first
            try:
                locator.wait_for(state="visible", timeout=500)
                return locator
            except Exception:
                pass
        wait_soft(page, 250)
    return None


def mark_export_controls(page: Any, marker: str) -> list[dict[str, str]]:
    return page.evaluate(
        """
        ([attr, marker]) => {
          const selector = `[${attr}]`;
          for (const previous of document.querySelectorAll(selector)) {
            previous.removeAttribute(attr);
          }

          const clickableSelector = [
            'a',
            'button',
            '[role="button"]',
            '[role="link"]',
            '[role="menuitem"]',
            '[data-rr-ui-dropdown-item]',
            '.dropdown-item'
          ].join(',');
          const nodeSelector = marker === 'plain-pdf'
            ? 'a,button,[role="button"],[role="link"],[role="menuitem"],li,span,div'
            : 'a,button,[role="button"],[role="link"],[role="menuitem"],img,svg,use,i,span';
          const blocked = [
            'logout',
            'my profile',
            'my home',
            'swift guidelines',
            'standards releases',
            'mt standards releases',
            'business domains',
            'change requests',
            'downloads',
            '#/help',
            '#/search',
            '#/c/',
            '#/iso20022'
          ];

          const visible = (el) => {
            const style = window.getComputedStyle(el);
            return style.visibility !== 'hidden'
              && style.display !== 'none'
              && Boolean(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          };
          const valueOf = (el) => [
            el.innerText || '',
            el.textContent || '',
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || '',
            el.getAttribute('alt') || '',
            el.getAttribute('class') || '',
            el.getAttribute('src') || '',
            el.href || el.getAttribute('href') || ''
          ].join(' ').replace(/\\s+/g, ' ').trim();

          const rows = [];
          const seen = new Set();
          for (const el of document.querySelectorAll(nodeSelector)) {
            if (!visible(el)) {
              continue;
            }
            const value = valueOf(el);
            const lower = value.toLowerCase();
            const isMatch = marker === 'plain-pdf'
              ? /plain\\s*pdf/i.test(value)
              : /(^|[^a-z])pdf([^a-z]|$)/i.test(value);
            if (!isMatch) {
              continue;
            }
            const target = el.closest(clickableSelector) || el;
            if (!visible(target) || seen.has(target)) {
              continue;
            }
            const targetValue = valueOf(target).toLowerCase();
            if (blocked.some((item) => targetValue.includes(item) || lower.includes(item))) {
              continue;
            }
            seen.add(target);
            target.setAttribute(attr, marker);
            rows.push({
              tag: target.tagName || '',
              role: target.getAttribute('role') || '',
              text: (target.innerText || target.textContent || '').trim(),
              ariaLabel: target.getAttribute('aria-label') || '',
              title: target.getAttribute('title') || '',
              className: target.getAttribute('class') || ''
            });
          }
          return rows;
        }
        """,
        [EXPORT_TARGET_ATTR, marker],
    )


def is_global_navigation_candidate(lower: str) -> bool:
    blocked = (
        "swift guidelines",
        "logged in as",
        "logout",
        "my profile",
        "my home",
        "downloads",
        "standards releases",
        "mt standards releases",
        "business domains",
        "change requests",
        "groups",
        "selection",
        "#/help",
        "#/search",
        "#/c/",
        "#/iso20022",
    )
    return any(item in lower for item in blocked)


def click_candidate_for_download(
    page: Any, candidate: Clickable, timeout_error_type: type[BaseException]
) -> Any:
    locator = page.locator(f'[data-swift-downloader-index="{candidate.index}"]').first
    before_pages = set(page.context.pages)
    try:
        with page.expect_download(timeout=DOWNLOAD_START_TIMEOUT_MS) as download_info:
            locator.click(timeout=10_000)
        return download_info.value
    except timeout_error_type:
        new_pages = [item for item in page.context.pages if item not in before_pages]
        for new_page in new_pages:
            try:
                nested = rank_download_candidates(collect_clickables(new_page))
                for nested_candidate in nested[:3]:
                    with new_page.expect_download(
                        timeout=DOWNLOAD_START_TIMEOUT_MS
                    ) as nested_download:
                        new_page.locator(
                            f'[data-swift-downloader-index="{nested_candidate.index}"]'
                        ).first.click(timeout=10_000)
                    new_page.close()
                    return nested_download.value
            finally:
                if not new_page.is_closed():
                    new_page.close()
        nested = rank_download_candidates(collect_clickables(page))
        for nested_candidate in nested[:3]:
            if nested_candidate.index == candidate.index:
                continue
            with page.expect_download(timeout=DOWNLOAD_START_TIMEOUT_MS) as nested_download:
                page.locator(
                    f'[data-swift-downloader-index="{nested_candidate.index}"]'
                ).first.click(timeout=10_000)
            return nested_download.value
        raise DownloaderError(
            f"Download did not begin after clicking {candidate.label!r}."
        ) from None


def safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return ".pdf"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise DownloaderError(f"Could not allocate a unique filename for {path.name}.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(argv)
        return MyStandardsDownloader(config).run()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
