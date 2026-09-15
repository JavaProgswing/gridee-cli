from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import pytest

import gridee_aiohttp as api
import gridee_booking_service as service
import gridee_wallet
from gridee_aiohttp import ApiError, GrideeClient
from gridee_booking_service import (
    booking_needs_rebook,
    booking_matches_saved_entry,
    booking_started,
    booking_body,
    find_booking_id,
    find_booking_record,
    find_booking_records,
    find_refund_transaction,
    choose,
    next_due,
    rebook_deadline,
    read_booking_config,
    replacement_booking_body,
    render,
    should_recover_booking,
    should_resume_monitoring,
    should_retry_invalid_date,
)


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


def test_client_forces_system_dns_resolver(monkeypatch):
    threaded_resolver = object()
    connector_calls = []

    class FakeClientSession:
        def __init__(self, **kwargs):
            self.headers = {}
            connector_calls.append(kwargs)

        async def close(self):
            pass

    async def fake_login(self):
        pass

    monkeypatch.setattr(api.aiohttp, "ThreadedResolver", lambda: threaded_resolver)
    monkeypatch.setattr(api.aiohttp, "TCPConnector", lambda **kwargs: ("connector", kwargs))
    monkeypatch.setattr(api.aiohttp, "ClientSession", FakeClientSession)
    monkeypatch.setattr(GrideeClient, "login", fake_login)

    async def open_client():
        async with GrideeClient("person@example.com", "secret"):
            pass

    asyncio.run(open_client())
    assert connector_calls[0]["connector"] == (
        "connector",
        {"resolver": threaded_resolver},
    )


def test_client_falls_back_to_firebase(monkeypatch):
    client = GrideeClient(" Person@Example.com ", "secret", firebase_key="public-key")
    client.session = FakeSession()  # type: ignore[assignment]
    calls = []

    async def fake_json(session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/api/auth/login"):
            raise ApiError("unauthorized", 401)
        if url.endswith("accounts:signInWithPassword"):
            return {"idToken": "firebase-token"}
        if url.endswith("accounts:lookup"):
            return {"users": [{"emailVerified": True}]}
        return {"token": "gridee-token", "tokenType": "Bearer"}

    monkeypatch.setattr(api, "_json", fake_json)
    asyncio.run(client.login())

    assert client.auth_method == "firebase"
    assert client.password == ""
    assert client.session.headers["Authorization"] == "Bearer gridee-token"
    assert calls[0][2]["json"]["email"] == "person@example.com"
    assert calls[-1][1].endswith("/api/auth/firebase/exchange")
    assert calls[-1][2]["json"] == {"idToken": "firebase-token"}


def test_http_error_names_safe_endpoint():
    class Response:
        status = 500

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self):
            return '{"error":"Internal Server Error"}'

    class Session:
        def request(self, *args, **kwargs):
            return Response()

    with pytest.raises(ApiError, match=r"POST /api/oauth2/user -> HTTP 500"):
        asyncio.run(api._json(Session(), "POST", "https://example.com/api/oauth2/user"))


def test_client_rejects_backslash_email_and_cross_origin():
    with pytest.raises(ApiError, match="not name"):
        GrideeClient(r"person\@example.com", "secret")
    client = GrideeClient("person@example.com", "secret")
    with pytest.raises(ApiError, match="outside"):
        client.url("https://example.com/private")


def test_render_booking_dates():
    value = {
        "checkInTime": "{date}T08:00:00",
        "checkOutTime": "{tomorrow}T17:00:00",
    }
    assert render(value, date(2026, 9, 13)) == {
        "checkInTime": "2026-09-13T08:00:00",
        "checkOutTime": "2026-09-14T17:00:00",
    }


def test_render_booking_offset(monkeypatch):
    monkeypatch.setattr(service, "local_utc_offset", lambda booking_date: "+05:30")
    assert render("{date}T08:00:00{offset}", date(2026, 9, 14)) == (
        "2026-09-14T08:00:00+05:30"
    )


def test_booking_body_requires_saved_values(monkeypatch):
    monkeypatch.setattr(service, "local_utc_offset", lambda booking_date: "+05:30")
    config = {
        "booking": {
            "spotId": "SAVE_SPOT_ID",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00",
            "checkOutTime": "{date}T17:00:00",
            "vehicleNumber": "KA01AA0001",
        }
    }
    with pytest.raises(RuntimeError, match="spotId"):
        booking_body(config, date(2026, 9, 13))

    config["booking"]["spotId"] = "spot-1"
    body = booking_body(config, date(2026, 9, 13))
    assert body["checkInTime"] == "2026-09-13T08:00:00+05:30"
    assert body["checkOutTime"] == "2026-09-13T17:00:00+05:30"


def test_partial_booking_config_fills_missing_defaults(tmp_path):
    path = tmp_path / "booking_service.json"
    path.write_text(
        json.dumps(
            {
                "userId": "current",
                "booking": {
                    "spotId": "ps5",
                    "lotId": "lot-1",
                    "vehicleNumber": "BR01BK2363",
                },
            }
        ),
        encoding="utf-8",
    )

    config = read_booking_config(path)

    assert config["userId"] == "current"
    assert config["booking"]["spotId"] == "ps5"
    assert config["booking"]["lotId"] == "lot-1"
    assert config["booking"]["vehicleNumber"] == "BR01BK2363"
    assert config["booking"]["checkInTime"] == "{date}T08:00:00{offset}"
    assert config["booking"]["checkOutTime"] == "{date}T17:00:00{offset}"
    assert config["rebook"]["refundWaitSeconds"] == 120


def test_next_due_uses_grace_and_at_most_once():
    tz = timezone(timedelta(hours=5, minutes=30))
    before = datetime(2026, 9, 13, 4, 0, tzinfo=tz)
    assert next_due(before, datetime.strptime("05:00", "%H:%M").time(), 10, "") == datetime(
        2026, 9, 13, 5, 0, tzinfo=tz
    )

    within_grace = datetime(2026, 9, 13, 5, 5, tzinfo=tz)
    assert next_due(within_grace, datetime.strptime("05:00", "%H:%M").time(), 10, "") == within_grace

    already_attempted = next_due(
        within_grace,
        datetime.strptime("05:00", "%H:%M").time(),
        10,
        "2026-09-13",
    )
    assert already_attempted == datetime(2026, 9, 14, 5, 0, tzinfo=tz)


def test_invalid_date_failure_gets_one_immediate_migration_retry():
    state = {
        "lastAttemptDate": "2026-09-14",
        "status": "failed",
        "error": "POST /api/bookings/user/create -> HTTP 400: Invalid date format",
    }
    assert should_retry_invalid_date(state, date(2026, 9, 14))
    state["formatRetryAttempted"] = True
    assert not should_retry_invalid_date(state, date(2026, 9, 14))


def test_booking_envelope_and_cancelled_status_are_detected():
    payload = {
        "data": {
            "booking": {
                "_id": "booking-7",
                "lotId": "lot-1",
                "spotId": "spot-1",
                "status": "cancelled",
            }
        }
    }
    record = find_booking_record(payload, "booking-7")
    assert record is not None
    assert find_booking_id(payload) == "booking-7"
    assert booking_needs_rebook(record)
    assert booking_needs_rebook({"id": "x", "status": "refunded"})
    assert booking_needs_rebook({"id": "x", "status": "cancelled_and_refunded"})
    assert booking_needs_rebook({"id": "x", "status": "ACTIVE", "cancelledAt": "now"})
    assert not booking_needs_rebook({"id": "x", "status": "CONFIRMED"})
    assert booking_started({"id": "x", "status": "ACTIVE"})
    assert booking_started({"id": "x", "actualCheckInTime": "2026-09-14T12:30:00"})
    assert not booking_started({"id": "x", "status": "CONFIRMED"})


def test_current_booking_discovery_matches_saved_entry():
    payload = {
        "data": {
            "items": [
                {
                    "id": "other",
                    "lotId": "lot-2",
                    "spotId": "spot-1",
                    "vehicleNumber": "KA01AA0001",
                    "checkInTime": "2026-09-14T08:00:00+05:30",
                    "status": "CONFIRMED",
                },
                {
                    "id": "wanted",
                    "lotId": "lot-1",
                    "spotId": "spot-1",
                    "vehicleNumber": "KA 01 AA 0001",
                    "checkInTime": "2026-09-14T12:40:00+05:30",
                    "status": "CONFIRMED",
                },
            ]
        }
    }
    body = {"lotId": "lot-1", "spotId": "spot-1", "vehicleNumber": "KA01AA0001"}
    matches = [
        record
        for record in find_booking_records(payload)
        if booking_matches_saved_entry(record, body, date(2026, 9, 14))
    ]
    assert [record["id"] for record in matches] == ["wanted"]


def test_refund_must_match_booking_and_be_finished():
    transactions = {
        "content": [
            {
                "id": "pending",
                "bookingId": "booking-7",
                "type": "REFUND",
                "status": "PENDING",
            },
            {
                "id": "other",
                "bookingId": "booking-8",
                "type": "REFUND",
                "status": "COMPLETED",
            },
            {
                "id": "refund-7",
                "bookingId": "booking-7",
                "type": "BOOKING_REFUND",
                "status": "COMPLETED",
            },
        ]
    }
    assert find_refund_transaction(transactions, "booking-7")["id"] == "refund-7"
    assert find_refund_transaction(transactions, "missing") is None


def test_rebook_monitor_can_resume_until_checkout():
    tz = timezone(timedelta(hours=5, minutes=30))
    config = {
        "rebook": {"enabled": True},
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "bookingId": "booking-1",
        "status": "monitoring",
    }
    now = datetime(2026, 9, 14, 7, 0, tzinfo=tz)
    assert rebook_deadline(config, now.date()) == datetime(2026, 9, 14, 17, 0, tzinfo=tz)
    assert should_resume_monitoring(config, state, now)
    assert not should_resume_monitoring(
        config, state, datetime(2026, 9, 14, 17, 0, tzinfo=tz)
    )
    assert should_recover_booking(config, {}, now, datetime.strptime("05:00", "%H:%M").time())
    assert not should_recover_booking(
        config,
        state,
        now,
        datetime.strptime("05:00", "%H:%M").time(),
    )


def test_late_rebook_moves_only_checkin_forward():
    tz = timezone(timedelta(hours=5, minutes=30))
    config = {
        "rebook": {"lateStartBufferMinutes": 5},
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    body = replacement_booking_body(
        config, date(2026, 9, 14), datetime(2026, 9, 14, 12, 31, 2, tzinfo=tz)
    )
    assert body["checkInTime"] == "2026-09-14T12:40:00+05:30"
    assert body["checkOutTime"] == "2026-09-14T17:00:00+05:30"


def test_cancelled_booking_is_rebooked_and_replacement_is_monitored(
    monkeypatch, tmp_path
):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        current = datetime(2026, 9, 14, 7, 59, 50, tzinfo=tz)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/wallet/transactions"):
                return {
                    "content": [
                        {
                            "id": "refund-1",
                            "bookingId": "cancelled-1",
                            "type": "REFUND",
                            "status": "COMPLETED",
                        }
                    ]
                }
            if path.endswith("/wallet"):
                return {"balance": 100}
            if method == "POST":
                return {
                    "id": "replacement-2",
                    "lotId": "lot-1",
                    "spotId": "spot-1",
                    "status": "CONFIRMED",
                }
            if path.endswith("/cancelled-1"):
                return {
                    "id": "cancelled-1",
                    "lotId": "lot-1",
                    "status": "CANCELLED",
                }
            return {
                "id": "replacement-2",
                "lotId": "lot-1",
                "status": "ACTIVE",
            }

    async def advance(seconds):
        Clock.current += timedelta(seconds=seconds)

    config = {
        "userId": "user-1",
        "rebook": {
            "enabled": True,
            "pollSeconds": 5,
            "retrySeconds": 5,
            "refundWaitSeconds": 5,
        },
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "bookingId": "cancelled-1",
        "status": "submitted",
    }
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service.asyncio, "sleep", advance)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(config, date(2026, 9, 14), state_path, state)
    )

    assert result["status"] == "booking-started"
    assert result["bookingId"] == "replacement-2"
    assert result["rebookAttempts"] == 1
    assert result["wasStarted"] is True
    assert result["refundTransactionId"] == "refund-1"
    assert ("POST", "/api/bookings/user-1/create") in calls


def test_rebook_409_adopts_existing_booking(monkeypatch, tmp_path):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        current = datetime(2026, 9, 14, 10, 0, tzinfo=tz)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/wallet/transactions"):
                return {
                    "content": [
                        {
                            "id": "refund-1",
                            "bookingId": "cancelled-1",
                            "type": "REFUND",
                            "status": "COMPLETED",
                        }
                    ]
                }
            if path.endswith("/wallet"):
                return {"balance": 100}
            if method == "POST":
                raise ApiError("Booking conflict", 409)
            if path.endswith("/all"):
                return {
                    "items": [
                        {
                            "id": "existing-replacement",
                            "lotId": "lot-1",
                            "spotId": "spot-1",
                            "vehicleNumber": "KA01AA0001",
                            "checkInTime": "2026-09-14T10:05:00+05:30",
                            "checkOutTime": "2026-09-14T17:00:00+05:30",
                            "status": "PENDING",
                        }
                    ]
                }
            if path.endswith("/cancelled-1"):
                return {"id": "cancelled-1", "status": "CANCELLED"}
            if path.endswith("/existing-replacement"):
                return {"id": "existing-replacement", "status": "ACTIVE"}
            raise AssertionError((method, path))

    config = {
        "userId": "user-1",
        "rebook": {"enabled": True, "pollSeconds": 5, "retrySeconds": 5},
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "bookingId": "cancelled-1",
        "status": "submitted",
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(
            config, date(2026, 9, 14), tmp_path / "state.json", state
        )
    )

    assert result["status"] == "booking-started"
    assert result["bookingId"] == "existing-replacement"
    assert result["rebookAttempts"] == 1
    assert sum(method == "POST" for method, _ in calls) == 1
    assert ("GET", "/api/bookings/user-1/all") in calls


def test_rebook_stops_once_rounded_start_reaches_checkout(monkeypatch, tmp_path):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 14, 16, 55, tzinfo=tz)

    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/wallet/transactions"):
                return {
                    "content": [
                        {
                            "id": "refund-1",
                            "bookingId": "cancelled-1",
                            "type": "REFUND",
                            "status": "COMPLETED",
                        }
                    ]
                }
            if path.endswith("/cancelled-1"):
                return {"id": "cancelled-1", "status": "CANCELLED"}
            raise AssertionError((method, path))

    config = {
        "userId": "user-1",
        "rebook": {
            "enabled": True,
            "pollSeconds": 5,
            "retrySeconds": 5,
            "lateStartBufferMinutes": 5,
        },
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "bookingId": "cancelled-1",
        "status": "submitted",
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(
            config, date(2026, 9, 14), tmp_path / "state.json", state
        )
    )

    assert result["status"] == "monitor-complete"
    assert result["rebookStoppedReason"] == (
        "Too late to create a replacement before check-out time."
    )
    assert "rebookAttempts" not in result
    assert not any(method == "POST" for method, _ in calls)


def test_cancelled_booking_without_refund_is_not_rebooked(monkeypatch, tmp_path):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        current = datetime(2026, 9, 14, 7, 59, 50, tzinfo=tz)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/wallet/transactions"):
                return {"content": []}
            return {
                "id": "cancelled-1",
                "lotId": "lot-1",
                "status": "CANCELLED",
            }

    async def advance(seconds):
        Clock.current += timedelta(seconds=seconds)

    config = {
        "userId": "user-1",
        "rebook": {
            "enabled": True,
            "pollSeconds": 5,
            "retrySeconds": 5,
            "refundWaitSeconds": 5,
        },
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T07:00:00+05:30",
            "checkOutTime": "{date}T08:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "bookingId": "cancelled-1",
        "status": "submitted",
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service.asyncio, "sleep", advance)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(
            config, date(2026, 9, 14), tmp_path / "state.json", state
        )
    )

    assert result["status"] == "cancelled-no-refund"
    assert "refundWaitExpiredAt" in result
    assert not any(method == "POST" for method, _ in calls)
    assert not should_resume_monitoring(config, result, Clock.current)
    assert not should_recover_booking(
        config, result, Clock.current, datetime.strptime("05:00", "%H:%M").time()
    )
    assert next_due(
        Clock.current,
        datetime.strptime("05:00", "%H:%M").time(),
        10,
        result["lastAttemptDate"],
    ) == datetime(2026, 9, 15, 5, 0, tzinfo=tz)


def test_restart_adopts_existing_booking_without_duplicate_post(monkeypatch, tmp_path):
    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            return {
                "items": [
                    {
                        "id": "existing-1",
                        "lotId": "lot-1",
                        "spotId": "spot-1",
                        "vehicleNumber": "KA01AA0001",
                        "checkInTime": "2026-09-14T08:00:00+05:30",
                        "checkOutTime": "2026-09-14T17:00:00+05:30",
                        "status": "CONFIRMED",
                    }
                ]
            }

    config = {
        "userId": "user-1",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.recover_or_create_booking(
            config, date(2026, 9, 14), tmp_path / "state.json"
        )
    )

    assert result["bookingId"] == "existing-1"
    assert result["recoveredOnRestart"] is True
    assert not any(method == "POST" for method, _ in calls)


def test_restart_adopts_same_day_booking_with_different_saved_details(monkeypatch, tmp_path):
    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            return {
                "items": [
                    {
                        "id": "existing-other-spot",
                        "lotId": "lot-2",
                        "spotId": "spot-9",
                        "vehicleNumber": "DIFFERENT",
                        "checkInTime": "2026-09-14T12:30:00+05:30",
                        "checkOutTime": "2026-09-14T17:00:00+05:30",
                        "status": "CONFIRMED",
                    }
                ]
            }

    config = {
        "userId": "user-1",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.recover_or_create_booking(
            config, date(2026, 9, 14), tmp_path / "state.json"
        )
    )

    assert result["bookingId"] == "existing-other-spot"
    assert result["recoveredOnRestart"] is True
    assert not any(method == "POST" for method, _ in calls)


def test_restart_creates_booking_when_current_list_is_empty(monkeypatch, tmp_path):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 14, 6, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/all"):
                return {"items": []}
            if path.endswith("/wallet"):
                return {"balance": 100}
            return {
                "id": "created-1",
                "lotId": "lot-1",
                "spotId": "spot-1",
                "vehicleNumber": "KA01AA0001",
                "checkInTime": "2026-09-14T08:00:00+05:30",
                "checkOutTime": "2026-09-14T17:00:00+05:30",
                "status": "CONFIRMED",
            }

    config = {
        "userId": "user-1",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.recover_or_create_booking(
            config, date(2026, 9, 14), tmp_path / "state.json"
        )
    )

    assert result["bookingId"] == "created-1"
    assert result["recoveredOnRestart"] is False
    assert ("GET", "/api/bookings/user-1/all") in calls
    assert ("POST", "/api/bookings/user-1/create") in calls


def test_restart_409_refetches_and_adopts_minimal_current_booking(monkeypatch, tmp_path):
    calls = []
    all_reads = 0

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(
                2026,
                9,
                14,
                10,
                30,
                tzinfo=timezone(timedelta(hours=5, minutes=30)),
            )

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            nonlocal all_reads
            calls.append((method, path))
            if path.endswith("/all"):
                all_reads += 1
                if all_reads == 1:
                    return {"items": []}
                return {
                    "items": [
                        {"bookingId": "existing-409", "status": "CONFIRMED"}
                    ]
                }
            if path.endswith("/wallet"):
                return {"balance": 100}
            if method == "POST":
                raise ApiError("Booking conflict", 409)
            raise AssertionError((method, path))

    config = {
        "userId": "user-1",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.recover_or_create_booking(
            config, date(2026, 9, 14), tmp_path / "state.json"
        )
    )

    assert result["bookingId"] == "existing-409"
    assert result["recoveredOnRestart"] is True
    assert sum(method == "POST" for method, _ in calls) == 1
    assert all_reads == 2


def test_unresolved_booking_conflict_does_not_retry_create_same_day():
    tz = timezone(timedelta(hours=5, minutes=30))
    now = datetime(2026, 9, 14, 10, 30, tzinfo=tz)
    config = {
        "booking": {"checkOutTime": "{date}T17:00:00+05:30"},
        "rebook": {"enabled": True},
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "status": "booking-conflict-unresolved",
    }

    assert not should_recover_booking(
        config, state, now, datetime.strptime("05:00", "%H:%M").time()
    )


def test_monitor_discards_old_booking_when_authenticated_account_changes(
    monkeypatch, tmp_path
):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 14, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    class Client:
        user = {"id": "new-user"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    config = {
        "userId": "current",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "userId": "old-user",
        "bookingId": "old-booking",
        "status": "monitoring",
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "new@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(
            config, date(2026, 9, 14), tmp_path / "state.json", state
        )
    )

    assert result["status"] == "account-changed"
    assert result["previousUserId"] == "old-user"
    assert result["userId"] == "new-user"
    assert "bookingId" not in result


def test_missing_booking_discards_stale_id_and_arms_recovery(monkeypatch, tmp_path):
    tz = timezone(timedelta(hours=5, minutes=30))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 14, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    calls = []

    class Client:
        user = {"id": "user-1"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/stale-booking"):
                raise ApiError("not found", 404)
            return {"items": []}

    config = {
        "userId": "current",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    state = {
        "lastAttemptDate": "2026-09-14",
        "userId": "user-1",
        "bookingId": "stale-booking",
        "status": "monitoring",
    }
    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    result = asyncio.run(
        service.monitor_and_rebook(
            config, date(2026, 9, 14), tmp_path / "state.json", state
        )
    )

    assert result["status"] == "missing-booking"
    assert result["missingBookingId"] == "stale-booking"
    assert "bookingId" not in result
    assert not any("wallet/transactions" in path for _, path in calls)
    assert should_recover_booking(
        config, result, Clock.now(), datetime.strptime("05:00", "%H:%M").time()
    )
    legacy_state = {
        "lastAttemptDate": "2026-09-14",
        "status": "cancelled-no-refund",
        "bookingStatus": "MISSING",
        "bookingId": "stale-booking",
    }
    assert should_recover_booking(
        config,
        legacy_state,
        Clock.now(),
        datetime.strptime("05:00", "%H:%M").time(),
    )


def test_restart_lookup_failure_never_submits_blindly(monkeypatch, tmp_path):
    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            raise ApiError("invalid user or unavailable lookup", 404)

    config = {
        "userId": "invalid-user",
        "booking": {
            "spotId": "bad-spot",
            "lotId": "bad-lot",
            "checkInTime": "{date}T08:00:00+05:30",
            "checkOutTime": "{date}T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")

    with pytest.raises(ApiError, match="invalid user"):
        asyncio.run(
            service.recover_or_create_booking(
                config, date(2026, 9, 14), tmp_path / "state.json"
            )
        )

    assert calls == [("GET", "/api/bookings/invalid-user/all")]


def test_choose_auto_multiple_and_manual(monkeypatch):
    assert choose("vehicle", [("one", "KA 01")]) == "one"

    answers = iter(["3", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert choose("vehicle", [("one", "KA 01"), ("two", "KA 02")]) == "two"

    monkeypatch.setattr("builtins.input", lambda prompt: "manual-id")
    assert choose("spot", []) == "manual-id"


def test_wallet_uses_one_client_for_current_user_and_history():
    class Client:
        user = {}

        def __init__(self):
            self.calls = []

        async def request(self, method, path):
            self.calls.append((method, path))
            if path == "/api/oauth2/user":
                return {"data": {"user": {"id": "user/7"}}}
            return {"path": path}

    client = Client()
    result = asyncio.run(gridee_wallet.fetch_wallet(client))
    assert result["userId"] == "user/7"
    assert client.calls == [
        ("GET", "/api/oauth2/user"),
        ("GET", "/api/users/user%2F7/wallet"),
        ("GET", "/api/users/user%2F7/wallet/transactions"),
    ]


def test_wallet_uses_explicit_user_id_without_profile_endpoint():
    class Client:
        user = {}

        def __init__(self):
            self.calls = []

        async def request(self, method, path):
            self.calls.append((method, path))
            return {"balance": "125.5"}

    client = Client()
    result = asyncio.run(gridee_wallet.fetch_wallet(client, "saved-user"))
    assert gridee_wallet.find_balance(result["wallet"]) == 125.5
    assert all(path != "/api/oauth2/user" for _, path in client.calls)


def test_booking_checks_wallet_before_submit(monkeypatch):
    calls = []

    class Client:
        user = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/wallet"):
                return {"balance": 100}
            return {"bookingId": "booking-1"}

    monkeypatch.setattr(service, "GrideeClient", lambda *args, **kwargs: Client())
    monkeypatch.setenv("GRIDEE_EMAIL", "person@example.com")
    monkeypatch.setenv("GRIDEE_PASSWORD", "secret")
    config = {
        "userId": "user-1",
        "booking": {
            "spotId": "spot-1",
            "lotId": "lot-1",
            "checkInTime": "2026-09-14T08:00:00+05:30",
            "checkOutTime": "2026-09-14T17:00:00+05:30",
            "vehicleNumber": "KA01AA0001",
        },
    }
    asyncio.run(service.submit(config, date(2026, 9, 14), False))
    assert calls == [
        ("GET", "/api/users/user-1/wallet"),
        ("POST", "/api/bookings/user-1/create"),
    ]
