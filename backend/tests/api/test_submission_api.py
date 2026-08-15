from tests.api.test_authoring_api import create_valid_mt541, login


def test_mock_uat_submission_requires_approval_external_validation_and_is_idempotent(
    client,
) -> None:
    author_headers = login(client, "author")
    draft_id, composed = create_valid_mt541(client, author_headers)

    submitter_headers = login(client, "submitter")
    blocked = client.post(
        f"/api/messages/{draft_id}/submit",
        json={"connectorId": "MOCK-UAT", "idempotencyKey": "SUBMIT-KEY-00000001"},
        headers=submitter_headers,
    )
    assert blocked.status_code == 400

    author_headers = login(client, "author")
    review = client.post(f"/api/messages/{draft_id}/review", headers=author_headers)
    assert review.status_code == 200

    approver_headers = login(client, "approver")
    approval = client.post(f"/api/messages/{draft_id}/approve", headers=approver_headers)
    assert approval.status_code == 200
    draft = client.get(f"/api/messages/drafts/{draft_id}").json()
    evidence = client.post(
        f"/api/external-validation/results/{draft_id}",
        json={
            "messageChecksum": composed["checksum"],
            "providerType": "TEST_MOCK_VALIDATOR",
            "profileId": draft["profileId"],
            "standardsRelease": draft["standardsRelease"],
            "passed": True,
            "validatedAt": "2026-08-05T12:00:00Z",
            "safeFindings": [],
        },
        headers=approver_headers,
    )
    assert evidence.status_code == 201, evidence.text

    submitter_headers = login(client, "submitter")
    payload = {"connectorId": "MOCK-UAT", "idempotencyKey": "SUBMIT-KEY-00000001"}
    submitted = client.post(
        f"/api/messages/{draft_id}/submit", json=payload, headers=submitter_headers
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["status"] == "ACKNOWLEDGED"
    assert body["safeResponseCode"] == "MOCK_UAT_ACCEPTED"
    assert body["acknowledgementReference"].startswith("MOCK-ACK-")
    repeated = client.post(
        f"/api/messages/{draft_id}/submit", json=payload, headers=submitter_headers
    )
    assert repeated.status_code == 200
    assert repeated.json()["submissionId"] == body["submissionId"]
    assert repeated.json()["attemptCount"] == 1


def test_download_only_connector_cannot_submit(client) -> None:
    author_headers = login(client, "author")
    draft_id, _ = create_valid_mt541(client, author_headers)
    author_headers = login(client, "author")
    client.post(f"/api/messages/{draft_id}/review", headers=author_headers)
    approver_headers = login(client, "approver")
    client.post(f"/api/messages/{draft_id}/approve", headers=approver_headers)
    submitter_headers = login(client, "submitter")
    response = client.post(
        f"/api/messages/{draft_id}/submit",
        json={
            "connectorId": "DOWNLOAD-ONLY",
            "idempotencyKey": "DOWNLOAD-KEY-000001",
        },
        headers=submitter_headers,
    )
    assert response.status_code == 400
    assert "Download-only" in response.json()["error"]["message"]
