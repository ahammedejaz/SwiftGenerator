from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.persistence.database import SessionLocal
from app.persistence.models import ReportRecord


class ReportRepository:
    def __init__(self) -> None:
        self._directory = Path(get_settings().report_directory).resolve()
        self._directory.mkdir(parents=True, exist_ok=True)

    def save_zip(self, content: bytes, payload: dict[str, Any]) -> str:
        report_id = str(uuid4())
        target = (self._directory / f"{report_id}.zip").resolve()
        if self._directory not in target.parents:
            raise ValueError("Invalid report artifact path")
        target.write_bytes(content)
        with SessionLocal.begin() as session:
            session.add(
                ReportRecord(
                    id=report_id,
                    scenario_id=None,
                    report_payload=payload,
                    artifact_path=str(target),
                )
            )
        return report_id

    def get_path(self, report_id: str) -> Path:
        with SessionLocal() as session:
            record = session.get(ReportRecord, report_id)
            if record is None or record.artifact_path is None:
                raise KeyError(f"Unknown report: {report_id}")
            path = Path(record.artifact_path).resolve()
            if self._directory not in path.parents or not path.is_file():
                raise KeyError(f"Report artifact is unavailable: {report_id}")
            return path

    def get_payload(self, report_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            record = session.get(ReportRecord, report_id)
            if record is None:
                raise KeyError(f"Unknown report: {report_id}")
            return record.report_payload


report_repository = ReportRepository()
