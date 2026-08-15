def test_demo_reset_seeds_repeatable_synthetic_dataset(client) -> None:
    first = client.post("/api/demo/reset")
    assert first.status_code == 200, first.text
    first_result = first.json()
    assert first_result["seededMessages"] == 15

    lifecycle = client.get(first_result["lifecyclePath"])
    assert lifecycle.status_code == 200
    assert [item["messageType"] for item in lifecycle.json()["entries"]] == [
        "MT541",
        "MT545",
        "MT548",
        "MT548",
        "MT548",
        "MT548",
    ]

    second = client.post("/api/demo/reset")
    assert second.status_code == 200
    assert second.json()["removedMessages"] == 15
    assert second.json()["seededMessages"] == 15
