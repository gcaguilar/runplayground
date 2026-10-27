"""M19 CSV import/export for registered training plans."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from app.services.plans_csv import MAX_CSV_BYTES
from app.utils import utcnow

HEADER = "session_date,type,intensity,distance_km,duration_min,status,notes"


def _plan_payload(**overrides) -> dict:
    today = utcnow().date()
    payload = {
        "name": "Autumn 10K block",
        "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": (today + timedelta(days=21)).isoformat(),
    }
    payload.update(overrides)
    return payload


def _create_plan(client, **overrides) -> dict:
    response = client.post("/api/v1/training-plans", json=_plan_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _add_session(client, plan: dict, **payload) -> dict:
    response = client.post(f"/api/v1/training-plans/{plan['id']}/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, content: str | bytes, *, filename="plan.csv", **data):
    body = content.encode("utf-8") if isinstance(content, str) else content
    return client.post(
        "/api/v1/training-plans/import",
        files={"file": (filename, body, "text/csv")},
        data={key: str(value) for key, value in data.items()},
    )


def _csv_text(*rows: str) -> str:
    return "\n".join([HEADER, *rows, ""])


def test_export_csv_header_rows_and_order(client):
    plan = _create_plan(client)
    a = plan["start_date"]
    _add_session(
        client,
        plan,
        session_date=a,
        type="rest",
        intensity="rest",
        distance_m=None,
        notes="Full rest",
    )
    _add_session(
        client,
        plan,
        session_date=a,
        type="easy",
        intensity="easy",
        distance_m=8000,
        duration_s=2700,
        notes="First, easy",
    )
    _add_session(
        client,
        plan,
        session_date=a,
        type="long",
        intensity="moderate",
        distance_m=21000,
        duration_s=7200,
    )

    response = client.get(f"/api/v1/training-plans/{plan['id']}/export.csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "autumn-10k-block" in disposition
    assert disposition.endswith('.csv"')

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "session_date",
        "type",
        "intensity",
        "distance_km",
        "duration_min",
        "status",
        "notes",
    ]
    # Same date is ordered by position, and the first easy session comes
    # before the long run because it was created first.
    assert [row[1] for row in rows[1:]] == ["rest", "easy", "long"]
    rest = rows[1]
    assert rest[3] == "" and rest[4] == ""
    easy = rows[2]
    assert easy[0] == a
    assert easy[3] == "8"
    assert easy[4] == "45"
    assert easy[6] == "First, easy"
    long = rows[3]
    assert long[3] == "21"
    assert long[4] == "120"


def test_export_csv_missing_plan_returns_404(client):
    response = client.get("/api/v1/training-plans/999999/export.csv")
    assert response.status_code == 404


def test_import_valid_csv_creates_plan_and_sessions(client):
    content = _csv_text(
        "2026-03-02,easy,easy,8,45,planned,First session",
        "2026-03-03,rest,rest,,,planned,",
        "2026-03-04,strength,moderate,,40,skipped,Strength",
    )
    response = _upload(client, content, name="Spring block")

    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["name"] == "Spring block"
    assert plan["source"] == "import"
    assert plan["start_date"] == "2026-03-02"
    assert plan["end_date"] == "2026-03-04"
    assert plan["is_active"] is False
    assert plan["sessions_total"] == 2
    assert len(plan["sessions"]) == 3
    assert [session["position"] for session in plan["sessions"]] == [1, 2, 3]
    assert plan["sessions"][0]["distance_m"] == 8000
    assert plan["sessions"][0]["duration_s"] == 2700
    assert plan["sessions"][0]["notes"] == "First session"
    assert plan["sessions"][1]["type"] == "rest"
    assert plan["sessions"][2]["status"] == "skipped"


def test_import_dry_run_does_not_write(client):
    content = _csv_text("2026-04-01,easy,easy,10,50,planned,")
    response = _upload(client, content, filename="preview.csv", dry_run="true")

    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["valid"] is True
    assert preview["plan_name"] == "preview"
    assert preview["start_date"] == preview["end_date"] == "2026-04-01"
    assert preview["row_count"] == 1
    assert preview["rows"][0]["distance_m"] == 10000
    assert preview["rows"][0]["duration_s"] == 3000
    assert preview["errors"] == []
    assert client.get("/api/v1/training-plans").json() == []


def test_import_invalid_row_rejects_everything(client):
    content = _csv_text(
        "2026-04-01,easy,easy,10,50,planned,",
        "2026-04-02,easy,easy,,,planned,No target",
    )
    preview = _upload(client, content, dry_run="true")
    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    assert preview.json()["row_count"] == 1
    assert [row["session_date"] for row in preview.json()["rows"]] == ["2026-04-01"]
    errors = preview.json()["errors"]
    assert any(error["line"] == 3 for error in errors)
    assert any("distance or duration" in error["message"] for error in errors)

    response = _upload(client, content)
    assert response.status_code == 422
    assert response.json()["valid"] is False
    assert client.get("/api/v1/training-plans").json() == []


def test_import_accepts_aliases_and_units(client):
    spanish = _csv_text(
        "2026-05-01,easy,easy,7500,2700,completed,Metros y segundos",
        "2026-05-02,rest,rest,,,,",
    ).replace(HEADER, "fecha,tipo,intensidad,distance_m,duration_s,estado,notas")
    response = _upload(client, spanish, filename="aliases.csv")
    assert response.status_code == 201, response.text
    sessions = response.json()["sessions"]
    assert sessions[0]["distance_m"] == 7500
    assert sessions[0]["duration_s"] == 2700
    assert sessions[0]["status"] == "completed"
    assert sessions[0]["notes"] == "Metros y segundos"
    assert sessions[1]["type"] == "rest"

    generic = _csv_text("2026-06-01,long,moderate,12.5,90,planned,").replace(
        HEADER, "date,type,intensity,distance,duration,status,notes"
    )
    response = _upload(client, generic, filename="generic-alias.csv")
    assert response.status_code == 201, response.text
    session = response.json()["sessions"][0]
    assert session["distance_m"] == 12500
    assert session["duration_s"] == 5400


def test_import_rejects_empty_header_and_inconsistent_rows(client):
    empty = _upload(client, b"")
    assert empty.status_code == 422
    assert "empty" in empty.text.lower()

    bad_header = _upload(client, "session_date,type\n2026-01-01,easy\n")
    assert bad_header.status_code == 422
    assert "Missing required column" in bad_header.text

    inconsistent = _upload(client, _csv_text("2026-01-01,easy,easy,5"))
    assert inconsistent.status_code == 422
    assert "Expected 7 columns" in inconsistent.text

    negative = _upload(client, _csv_text("2026-01-01,easy,easy,-5,30,planned,"))
    assert negative.status_code == 422
    assert "positive" in negative.text

    no_rows = _upload(client, HEADER + "\n")
    assert no_rows.status_code == 422
    assert client.get("/api/v1/training-plans").json() == []


def test_import_rejects_more_than_400_rows(client):
    rows = [f"2026-01-{(index % 28) + 1:02d},easy,easy,5,30,planned," for index in range(401)]
    response = _upload(client, _csv_text(*rows))
    assert response.status_code == 422
    assert "at most 400" in response.text
    assert client.get("/api/v1/training-plans").json() == []


def test_import_rejects_oversized_file(client):
    response = _upload(client, b"x" * (MAX_CSV_BYTES + 1))
    assert response.status_code == 413


def test_import_activate_replaces_previous_plan(client):
    first = _upload(
        client,
        _csv_text("2026-07-01,easy,easy,5,30,planned,"),
        name="First",
        activate="true",
    )
    assert first.status_code == 201, first.text
    assert first.json()["is_active"] is True

    second = _upload(
        client,
        _csv_text("2026-08-01,easy,easy,6,35,planned,"),
        name="Second",
        activate="true",
    )
    assert second.status_code == 201, second.text
    assert second.json()["is_active"] is True

    inactive = _upload(
        client,
        _csv_text("2026-09-01,easy,easy,7,40,planned,"),
        name="Third",
        activate="false",
    )
    assert inactive.status_code == 201
    assert inactive.json()["is_active"] is False

    listing = client.get("/api/v1/training-plans").json()
    active = [item["name"] for item in listing if item["is_active"]]
    assert active == ["Second"]


def test_export_import_roundtrip(client):
    plan = _create_plan(client, name="Round trip")
    start = plan["start_date"]
    _add_session(
        client,
        plan,
        session_date=start,
        type="easy",
        intensity="easy",
        distance_m=12345,
        duration_s=3600,
        status="completed",
        notes="Easy, relaxed",
    )
    _add_session(
        client,
        plan,
        session_date=start,
        type="rest",
        intensity="rest",
        distance_m=None,
        notes="Rest day",
    )

    exported = client.get(f"/api/v1/training-plans/{plan['id']}/export.csv")
    assert exported.status_code == 200
    imported = _upload(client, exported.content, filename="round-trip.csv")
    assert imported.status_code == 201, imported.text
    payload = imported.json()
    assert payload["name"] == "round-trip"
    assert payload["source"] == "import"
    assert [
        (item["type"], item["intensity"], item["distance_m"]) for item in payload["sessions"]
    ] == [
        ("easy", "easy", 12345),
        ("rest", "rest", None),
    ]
    assert payload["sessions"][0]["duration_s"] == 3600
    assert payload["sessions"][0]["notes"] == "Easy, relaxed"
