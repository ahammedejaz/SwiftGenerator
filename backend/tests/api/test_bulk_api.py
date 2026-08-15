from io import BytesIO
from zipfile import ZipFile

from openpyxl import Workbook

from app.bulk.service import REQUIRED_HEADERS

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_template_bulk_generation_and_zip_export(client) -> None:
    template = client.get("/api/bulk/template")
    assert template.status_code == 200
    assert template.content.startswith(b"PK")

    response = client.post(
        "/api/bulk/generate",
        files={"file": ("synthetic-scenarios.xlsx", template.content, XLSX_MIME)},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["totalRows"] == 4
    assert result["generatedRows"] == 3
    assert result["failedRows"] == 1
    assert [row["status"] for row in result["rowResults"]] == [
        "GENERATED",
        "GENERATED",
        "GENERATED",
        "FAILED",
    ]

    metadata = client.get(f"/api/reports/{result['reportId']}/metadata")
    assert metadata.status_code == 200
    assert metadata.json()["reportPayload"]["generatedRows"] == 3

    download = client.get(result["downloadPath"])
    assert download.status_code == 200
    with ZipFile(BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert "summary.xlsx" in names
        assert "execution-report.json" in names
        assert len([name for name in names if name.endswith(".txt")]) == 3
        assert len([name for name in names if name.endswith(".validation.json")]) == 3


def test_bulk_rejects_missing_mandatory_headers(client) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(REQUIRED_HEADERS[:-1])
    output = BytesIO()
    workbook.save(output)
    response = client.post(
        "/api/bulk/generate",
        files={"file": ("missing-header.xlsx", output.getvalue(), XLSX_MIME)},
    )
    assert response.status_code == 400
    assert "Missing mandatory Excel columns" in response.json()["error"]["message"]


def test_bulk_rejects_unsupported_and_path_traversal_uploads(client) -> None:
    executable = client.post(
        "/api/bulk/generate",
        files={"file": ("payload.exe", b"MZ executable", "application/octet-stream")},
    )
    assert executable.status_code == 400

    template = client.get("/api/bulk/template").content
    traversal = client.post(
        "/api/bulk/generate",
        files={"file": ("../escape.xlsx", template, XLSX_MIME)},
    )
    assert traversal.status_code == 400
    assert "path component" in traversal.json()["error"]["message"]


def test_bulk_rejects_oversized_upload(client) -> None:
    oversized = b"PK" + (b"0" * (5_242_880 + 1))
    response = client.post(
        "/api/bulk/generate",
        files={"file": ("oversized.xlsx", oversized, XLSX_MIME)},
    )
    assert response.status_code == 400
    assert "upload limit" in response.json()["error"]["message"]
