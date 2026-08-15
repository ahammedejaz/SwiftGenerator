from app.persistence.database import SessionLocal
from app.persistence.models import DraftFieldRecord

MT541_VALUES = {
    "MT541-A-20C-SEME": "CLIENTREF000001",
    "MT541-A-23G-NONE": "NEWM",
    "MT541-B-98A-TRAD": "20260803",
    "MT541-B-98A-SETT": "20260806",
    "MT541-B-35B-NONE": "ISIN XS0000000001",
    "MT541-B-36B-SETT": "UNIT/1000,",
    "MT541-B-22F-SETR": "BUY",
    "MT541-C-97A-SAFE": "REALSAFEACCOUNT001",
    "MT541-E-22F-SETR": "RECE",
    "MT541-E-95R-PSET": "CLIENTPSET01",
    "MT541-E-95R-DEAG": "ZZZZUS00DEMO",
    "MT541-E-95R-REAG": "YYYYGB00DEMO",
    "MT541-E-19A-SETT": "USD25000,00",
}


def login(client, identity: str) -> dict[str, str]:
    response = client.post("/api/auth/development-login", json={"identity": identity})
    assert response.status_code == 200
    token = client.cookies.get("swift_platform_csrf")
    assert token
    return {"X-CSRF-Token": token}


def create_valid_mt541(client, headers: dict[str, str]) -> tuple[str, dict[str, object]]:
    response = client.post(
        "/api/messages/drafts",
        json={"messageType": "MT541", "profileId": "BASE_DEMO_V1"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    draft_id = draft["draftId"]
    sequences = {item["sequencePath"]: item["sequenceId"] for item in draft["sequences"]}
    for row_id, value in MT541_VALUES.items():
        sequence_path = row_id.split("-")[1]
        updated = client.post(
            f"/api/messages/drafts/{draft_id}/fields",
            json={
                "rowId": row_id,
                "sequenceId": sequences[sequence_path],
                "value": value,
                "source": "USER_ENTERED",
                "confirmed": True,
            },
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
    composed = client.post(f"/api/messages/{draft_id}/compose", headers=headers)
    assert composed.status_code == 200, composed.text
    return draft_id, composed.json()


def test_real_data_draft_is_encrypted_composed_and_downloaded(client) -> None:
    headers = login(client, "author")
    draft_id, composed = create_valid_mt541(client, headers)
    assert composed["validationLevels"]["STRUCTURE_VALID"] == "PASSED"
    assert ":20C::SEME//CLIENTREF000001" in composed["block4"]
    assert composed["capability"] == "PARTIAL"
    with SessionLocal() as session:
        records = session.query(DraftFieldRecord).filter_by(draft_id=draft_id).all()
        assert len(records) == len(MT541_VALUES)
        assert all("REALSAFEACCOUNT001" not in item.encrypted_value for item in records)
    block4 = client.get(f"/api/messages/{draft_id}/downloads/block4")
    assert block4.status_code == 200
    assert block4.text.startswith("{4:\n")
    fin = client.post(
        f"/api/messages/{draft_id}/exports/fin",
        json={
            "outputMode": "FIN_APPLICATION_MESSAGE",
            "senderLogicalTerminal": "ZZZZUS00XXXX",
            "receiverAddress": "YYYYGB00XXXX",
            "sessionNumber": "0001",
            "sequenceNumber": "000001",
            "messageUserReference": "CLIENTMUR0001",
        },
        headers=headers,
    )
    assert fin.status_code == 200, fin.text
    assert fin.text.startswith("{1:F01ZZZZUS00XXXX0001000001}{2:I541YYYYGB00XXXXN}")
    evidence = client.get(f"/api/messages/{draft_id}/downloads/evidence-zip")
    assert evidence.status_code == 200
    assert evidence.headers["content-type"] == "application/zip"


def test_csrf_tenant_isolation_and_maker_checker(client) -> None:
    author_headers = login(client, "author")
    denied = client.post(
        "/api/messages/drafts",
        json={"messageType": "MT541", "profileId": "BASE_DEMO_V1"},
    )
    assert denied.status_code == 403
    draft_id, composed = create_valid_mt541(client, author_headers)
    review = client.post(f"/api/messages/{draft_id}/review", headers=author_headers)
    assert review.status_code == 200

    other_headers = login(client, "other-author")
    assert other_headers
    hidden = client.get(f"/api/messages/drafts/{draft_id}")
    assert hidden.status_code == 404

    approver_headers = login(client, "approver")
    approval = client.post(f"/api/messages/{draft_id}/approve", headers=approver_headers)
    assert approval.status_code == 200, approval.text
    assert approval.json()["checksum"] == composed["checksum"]

    author_headers = login(client, "author")
    draft = client.get(f"/api/messages/drafts/{draft_id}").json()
    field_id = next(
        item["fieldId"] for item in draft["fields"] if item["rowId"] == "MT541-A-20C-SEME"
    )
    removed = client.delete(
        f"/api/messages/drafts/{draft_id}/fields/{field_id}", headers=author_headers
    )
    assert removed.status_code == 200
    assert removed.json()["status"] == "DRAFT"
    assert removed.json()["currentChecksum"] is None


def test_rje_is_fail_closed_without_authorised_contract(client) -> None:
    headers = login(client, "author")
    draft_id, _ = create_valid_mt541(client, headers)
    response = client.post(
        f"/api/messages/{draft_id}/exports/rje",
        json={
            "outputMode": "RJE_SINGLE",
            "senderLogicalTerminal": "ZZZZUS00XXXX",
            "receiverAddress": "YYYYGB00XXXX",
            "sessionNumber": "0001",
            "sequenceNumber": "000001",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_client_profile_overlay_changes_required_field_and_validation(client) -> None:
    headers = login(client, "author")
    created = client.post(
        "/api/messages/drafts",
        json={"messageType": "MT541", "profileId": "BFS_CLIENT_DEMO_V1"},
        headers=headers,
    ).json()
    draft_id = created["draftId"]
    sequences = {item["sequencePath"]: item["sequenceId"] for item in created["sequences"]}
    values = MT541_VALUES | {
        "MT541-A-20C-SEME": "CLIENTREF01",
        "MT541-E-95R-PSET": "CLIENTPSET01",
    }
    for row_id, value in values.items():
        saved = client.post(
            f"/api/messages/drafts/{draft_id}/fields",
            json={
                "rowId": row_id,
                "sequenceId": sequences[row_id.split("-")[1]],
                "value": value,
            },
            headers=headers,
        )
        assert saved.status_code == 200
    invalid = client.post(f"/api/messages/{draft_id}/compose", headers=headers).json()
    assert invalid["validationLevels"]["STRUCTURE_VALID"] == "FAILED"
    assert any("MT541-A-20C-COMM" in item for item in invalid["findings"])
    saved = client.post(
        f"/api/messages/drafts/{draft_id}/fields",
        json={
            "rowId": "MT541-A-20C-COMM",
            "sequenceId": sequences["A"],
            "value": "CLIENTCOMM01",
        },
        headers=headers,
    )
    assert saved.status_code == 200
    valid = client.post(f"/api/messages/{draft_id}/compose", headers=headers).json()
    assert valid["validationLevels"]["STRUCTURE_VALID"] == "PASSED"
    assert valid["validationLevels"]["CLIENT_PROFILE_VALID"] == "PASSED"


def test_draft_profile_can_be_changed_and_invalidates_prior_validation(client) -> None:
    headers = login(client, "author")
    draft_id, _ = create_valid_mt541(client, headers)
    before = client.get(f"/api/messages/drafts/{draft_id}").json()
    changed = client.patch(
        f"/api/messages/drafts/{draft_id}",
        json={"profileId": "BFS_CLIENT_DEMO_V1"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    payload = changed.json()
    assert payload["profileId"] == "BFS_CLIENT_DEMO_V1"
    assert payload["revision"] == before["revision"] + 1
    assert payload["status"] == "DRAFT"
    assert payload["currentChecksum"] is None
