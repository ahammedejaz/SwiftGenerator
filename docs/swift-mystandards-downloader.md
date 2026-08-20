# SWIFT MyStandards MT Downloader

Local operator utility for downloading authorised SWIFT MyStandards MT `2026.November`
message reference documents through a headed browser.

It does not bypass login, MFA, CAPTCHA or access controls. The authenticated MyStandards
catalogue is the only discovery authority.

## Requirements

- Authorised SWIFT/MyStandards account.
- Python development environment from this repository.
- Python Playwright and Chromium:

```bash
make install
python -m playwright install chromium
```

## Environment

Add credentials to local `.env` only:

```dotenv
SWIFT_MYSTANDARDS_EMAIL=
SWIFT_MYSTANDARDS_PASSWORD=
```

Existing local aliases `SWIFT_EMAIL` and `SWIFT_PASSWORD` are also accepted, but the
explicit MyStandards names are preferred for new setups.

The downloader never prints the password and does not write credentials, cookies, storage
state, HAR files or traces to Git.

## Run

Default target:

- Format: `MT`
- Release: `2026.November`
- URL: `https://www2.swift.com/mystandards/#/mtcategories/mt/2026.November`
- Output: `~/Downloads/SWIFT_MT_2026_November/`

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py
```

Operator Make target using `--keep-session`:

```bash
make swift-mt-download
```

## MFA Workflow

The browser launches headed. The script attempts normal first-factor login using the
configured email/password. If MFA, CAPTCHA or an SSO flow needs manual work, the terminal
prints the manual verification prompt and blocks on `ENTER`.

Complete verification in the same browser, wait until MyStandards is visible, then press
`ENTER` in the terminal. The script re-checks authentication before continuing.

## Dry Run

Authenticates and discovers the catalogue without downloading:

```bash
make swift-mt-discover
```

or:

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py --dry-run
```

## Single Message Test

Useful before the full run:

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py --category 5 --message MT541
```

Do not use these filters for the final complete run.

## Full Download

Run without filters:

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py
```

Recommended for the long SWIFT run so the same browser profile can be reused after an
interruption:

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py --keep-session
```

The downloader discovers all categories and messages dynamically from the authenticated
MyStandards page. It logs in once, scans each category, and then downloads every discovered
message in one sequential loop through the same browser context. It does not contain a
hardcoded MT message list.

For each message page the download flow is:

1. Click `Export`.
2. Click the visible `PDF` icon/button/menu item.
3. Click `Plain PDF`.
4. Save and validate the resulting PDF.

## Resume And Retry

After each item the manifest is atomically written:

- `manifest.json`
- `manifest.csv`
- `failures.json`
- `download-report.md`

Already verified successful downloads are skipped on the next run. Use:

```bash
backend/.venv/bin/python tools/swift-mystandards-downloader/swift_mystandards_downloader.py --retry-failed
```

Use `--force` only when intentionally redownloading.

## Output Structure

Default output:

```text
~/Downloads/SWIFT_MT_2026_November/
├── Category_0_...
├── Category_1_...
├── ...
├── debug/
├── failures.json
├── manifest.csv
├── manifest.json
└── download-report.md
```

Category names come from the website and are sanitised for the filesystem.

## Validation

For each file the downloader records:

- file size
- SHA-256
- original and saved filename
- status and attempts
- source page
- message/category metadata

PDF downloads must be non-empty and start with `%PDF`. Where text extraction is available,
the tool checks for the expected MT message identity and the `2026.November` release.
HTML login/error pages saved as files are rejected.

## Security Notes

- `.env` is ignored.
- Downloaded SWIFT documents stay under `~/Downloads/`, not the repository.
- Browser session state is transient by default.
- `--keep-session` stores a profile under the output directory, still outside Git by default.
- Do not copy source PDFs into the repository automatically.

## Later Knowledge Base Use

After the download is complete, the operator can manually choose which licensed documents
to copy into `swiftKnowledgeBase/`. That folder is ignored and remains operator-owned.
