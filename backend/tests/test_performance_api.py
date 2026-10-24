from __future__ import annotations


def _upload_fit(client, sample_fit):
    response = client.post(
        "/api/v1/imports",
        files=[("files", ("sample.fit", sample_fit, "application/octet-stream"))],
    )
    assert response.status_code == 200
    return response.json()["results"][0]["activity_id"]


def _distance(overview, key):
    return next(item for item in overview["distances"] if item["distance_key"] == key)


def test_performance_overview_from_fit_stream(client, sample_fit):
    activity_id = _upload_fit(client, sample_fit)

    response = client.get("/api/v1/performance")
    assert response.status_code == 200
    overview = response.json()

    assert overview["status"] == "ok"
    assert overview["model_version"]
    assert overview["data"]["running_activities"] == 1
    assert overview["data"]["activities_with_streams"] == 1
    assert overview["data"]["efforts"] == 1
    assert overview["fitness_anchor"] is not None
    assert overview["fitness_anchor"]["distance_m"] == 10000

    five = _distance(overview, "5k")
    assert five["status"] == "ok"
    assert five["official_pr"] is None
    assert five["recent_best"]["activity_id"] == activity_id
    assert five["recent_best"]["duration_s"] == 1800
    assert five["planning"]["time_s"] == 1800
    assert five["planning"]["low_s"] < 1800 < five["planning"]["high_s"]
    assert five["ceiling"]["time_s"] == 1800
    assert five["gap_pct"] == 0
    assert five["confidence"] in {"low", "medium"}
    assert "single_effort" in five["confidence_reasons"]

    ten = _distance(overview, "10k")
    assert ten["planning"]["time_s"] > five["planning"]["time_s"]
    assert ten["status"] == "ok"

    assert "no_races" in overview["warnings"]
    assert "no_garmin_export" in overview["warnings"]


def test_marking_activity_as_race_creates_official_pr(client, sample_fit):
    activity_id = _upload_fit(client, sample_fit)
    client.get("/api/v1/performance")

    response = client.patch(
        f"/api/v1/activities/{activity_id}",
        json={"is_race": True, "name": "Spring 5K"},
    )
    assert response.status_code == 200

    overview = client.get("/api/v1/performance").json()
    five = _distance(overview, "5k")
    assert five["official_pr"] is not None
    assert five["official_pr"]["activity_id"] == activity_id
    assert five["official_pr"]["duration_s"] == 1800
    assert "race_at_distance" in five["confidence_reasons"]
    assert "no_races" not in overview["warnings"]


def test_goals_crud_and_gap(client, sample_fit):
    _upload_fit(client, sample_fit)

    response = client.put(
        "/api/v1/performance/goals/5k",
        json={
            "target_time_s": 1680,
            "target_date": "2027-03-01",
            "race_name": "Spring 5K",
        },
    )
    assert response.status_code == 200
    goal = response.json()
    assert goal["distance_m"] == 5000
    assert goal["target_time_s"] == 1680
    assert goal["race_name"] == "Spring 5K"

    goals = client.get("/api/v1/performance/goals").json()
    assert len(goals) == 1

    overview = client.get("/api/v1/performance").json()
    five = _distance(overview, "5k")
    assert five["goal"]["target_time_s"] == 1680
    assert five["goal_gap_s"] == -120
    assert five["goal_gap_pct"] == -6.7

    updated = client.put(
        "/api/v1/performance/goals/10k",
        json={"target_time_s": 3600},
    )
    assert updated.status_code == 200
    assert len(client.get("/api/v1/performance/goals").json()) == 2

    assert client.delete("/api/v1/performance/goals/5k").status_code == 204
    assert client.delete("/api/v1/performance/goals/5k").status_code == 404
    assert len(client.get("/api/v1/performance/goals").json()) == 1

    assert (
        client.put("/api/v1/performance/goals/800m", json={"target_time_s": 180}).status_code == 404
    )


def test_history_and_recompute(client, sample_fit):
    _upload_fit(client, sample_fit)
    client.get("/api/v1/performance")

    history = client.get("/api/v1/performance/history?days=30")
    assert history.status_code == 200
    payload = history.json()
    assert payload["days"] == 30
    assert len(payload["items"]) == 1
    assert payload["items"][0]["fitness_anchor_s"] is not None
    assert 3000 < payload["items"][0]["fitness_anchor_s"] < 5000
    assert len(payload["items"][0]["predictions"]) == 4

    response = client.post("/api/v1/performance/recompute")
    assert response.status_code == 200
    result = response.json()
    assert result["activities"] == 1
    assert result["efforts"] == 1
    assert result["overview"]["fitness_anchor"] is not None


def test_reference_is_empty_without_export(client):
    response = client.get("/api/v1/performance/reference")
    assert response.status_code == 200
    assert response.json()["imported_at"] is None
    assert response.json()["race_predictions"] == []
