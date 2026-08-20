from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gridee import api
from gridee.api import ApiClient, ApiError, SessionStore
from gridee.cli import make_parser


class FakeResponse:
    def __init__(self, value):
        self.payload = json.dumps(value).encode()
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_login_then_authenticated_request(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.full_url.endswith("/api/auth/login"):
            assert request.get_header("Authorization") is None
            assert json.loads(request.data) == {"email": "person@example.com", "password": "secret"}
            return FakeResponse({"token": "jwt-value", "tokenType": "Bearer", "user": {"id": 7}})
        assert request.get_header("Authorization") == "Bearer jwt-value"
        return FakeResponse({"id": 7})

    monkeypatch.setattr(api, "urlopen", fake_urlopen)
    client = ApiClient()
    login = client.login("person@example.com", "secret")
    user = client.request("GET", "/api/oauth2/user")
    assert login["user"]["id"] == 7
    assert user == {"id": 7}
    assert len(requests) == 2


def test_refuses_cross_origin_url():
    client = ApiClient(token="jwt-value")
    with pytest.raises(ApiError, match="outside"):
        client.request("GET", "https://example.com/private")


def test_session_store_round_trip(tmp_path: Path):
    store = SessionStore(tmp_path / "nested" / "session.json")
    store.save({"token": "abc", "tokenType": "Bearer"})
    assert store.load()["token"] == "abc"
    assert store.clear() is True
    assert store.load() == {}


def test_api_request_parser_supports_manual_auth_and_json():
    args = make_parser().parse_args(
        [
            "api",
            "request",
            "/api/bookings/my-bookings",
            "--method",
            "POST",
            "--email",
            "person@example.com",
            "--password",
            "secret",
            "--data",
            '{"active": true}',
        ]
    )
    assert args.api_command == "request"
    assert args.email == "person@example.com"
    assert args.method == "POST"


def test_auth_login_parser_supports_password_stdin():
    args = make_parser().parse_args(
        ["auth", "login", "--email", "person@example.com", "--password-stdin"]
    )
    assert args.password_stdin is True
    assert args.email == "person@example.com"


def test_saved_token_is_not_reused_for_another_origin(tmp_path: Path):
    session_file = tmp_path / "session.json"
    SessionStore(session_file).save(
        {"baseUrl": "https://gridee.onrender.com", "token": "sensitive-token"}
    )
    args = SimpleNamespace(
        session_file=session_file,
        token=None,
        token_type=None,
        base_url="https://example.com",
        api_timeout=30,
        email=None,
    )
    client, _ = api.authenticated_client(args)
    assert client.token is None


class RecordingClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return {"accepted": True}


def test_wallet_topup_preview_does_not_send(monkeypatch, capsys):
    client = RecordingClient()
    monkeypatch.setattr(api, "authenticated_client", lambda args: (client, None))
    args = make_parser().parse_args(
        ["api", "wallet-topup", "--user-id", "user-7", "--amount", "125"]
    )
    assert api.run_api(args) == 0
    assert client.calls == []
    output = json.loads(capsys.readouterr().out)
    assert output["dryRun"] is True
    assert output["body"] == {"amount": 125.0}


def test_wallet_topup_execute_posts_validated_amount(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(api, "authenticated_client", lambda args: (client, None))
    args = make_parser().parse_args(
        [
            "api",
            "wallet-topup",
            "--user-id",
            "user/with space",
            "--amount",
            "125.50",
            "--execute",
        ]
    )
    assert api.run_api(args) == 0
    assert client.calls == [
        (
            "POST",
            "/api/users/user%2Fwith%20space/wallet/topup",
            {"body": {"amount": 125.5}},
        )
    ]


@pytest.mark.parametrize("amount", ["0", "-1", "nan", "inf"])
def test_wallet_topup_rejects_invalid_amount(monkeypatch, amount):
    client = RecordingClient()
    monkeypatch.setattr(api, "authenticated_client", lambda args: (client, None))
    args = make_parser().parse_args(
        ["api", "wallet-topup", "--user-id", "user-7", "--amount", amount]
    )
    with pytest.raises(ApiError, match="greater than zero"):
        api.run_api(args)
    assert client.calls == []


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"id": "direct-id"}, "direct-id"),
        ({"data": {"user": {"userId": 42}}}, "42"),
        ({"principal": {"sub": "subject-id"}}, "subject-id"),
    ],
)
def test_extract_user_id_from_current_user_wrappers(payload, expected):
    assert api.extract_user_id(payload) == expected


def test_wallet_topup_defaults_to_current_account(monkeypatch):
    client = RecordingClient(
        [{"data": {"user": {"id": "current-user"}}}, {"accepted": True}]
    )
    monkeypatch.setattr(api, "authenticated_client", lambda args: (client, None))
    args = make_parser().parse_args(
        ["api", "wallet-topup", "--amount", "75", "--execute"]
    )
    assert api.run_api(args) == 0
    assert client.calls == [
        ("GET", "/api/oauth2/user", {}),
        (
            "POST",
            "/api/users/current-user/wallet/topup",
            {"body": {"amount": 75.0}},
        ),
    ]


def test_wallet_command_defaults_to_current_account(monkeypatch):
    client = RecordingClient([{"id": "current-user"}, {"balance": 75.0}])
    monkeypatch.setattr(api, "authenticated_client", lambda args: (client, None))
    args = make_parser().parse_args(["api", "wallet"])
    assert api.run_api(args) == 0
    assert client.calls == [
        ("GET", "/api/oauth2/user", {}),
        ("GET", "/api/users/current-user/wallet", {}),
    ]
