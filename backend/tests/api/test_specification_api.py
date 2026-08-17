from app.domain.enums import MessageType
from app.specifications.registry import specification_registry


def test_specification_catalogue_is_honest_about_partial_coverage(client) -> None:
    response = client.get("/api/specifications/messages")
    assert response.status_code == 200
    body = response.json()
    assert len(body["supported"]) == 16
    assert all(item["capability"] == "PARTIAL" for item in body["supported"])
    assert all(
        item["message"] == "Specification visible; generation not implemented."
        for item in body["catalogueOnly"]
    )


def test_specification_and_coverage_endpoints(client) -> None:
    specification = client.get("/api/specifications/messages/MT537")
    assert specification.status_code == 200
    # Derived, not restated: a hardcoded count turns "someone edited the YAML" into a
    # failure that says nothing about what actually changed.
    assert len(specification.json()["fields"]) == len(
        specification_registry.get(MessageType.MT537).fields
    )
    coverage = client.get("/api/specifications/messages/MT537/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["productionGatePassed"] is False
    report = client.get("/api/specifications/coverage")
    assert report.status_code == 200
    assert report.json()["totalConfiguredRows"] == sum(
        specification_registry.statistics().values()
    )
