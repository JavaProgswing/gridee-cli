from __future__ import annotations

import getpass
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://gridee.onrender.com"


class ApiError(RuntimeError):
    """A readable error returned by the Gridee HTTP API or transport."""


def default_session_file() -> Path:
    root = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CONFIG_HOME")
    if root:
        return Path(root) / "gridee-cli" / "session.json"
    return Path.home() / ".config" / "gridee-cli" / "session.json"


@dataclass
class SessionStore:
    path: Path

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise ApiError(f"Could not read session file {self.path}: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def clear(self) -> bool:
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False


class ApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        token: str | None = None,
        token_type: str = "Bearer",
        timeout: float = 30.0,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError("API base URL must be an http(s) URL.")
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.token_type = token_type or "Bearer"
        self.timeout = timeout
        self.last_login_response: dict[str, Any] = {}

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Iterable[tuple[str, str]] = (),
        headers: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> Any:
        relative = path.lstrip("/")
        url = urljoin(self.base_url, relative)
        base = urlparse(self.base_url)
        target = urlparse(url)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise ApiError("Refusing to send credentials outside the configured API origin.")
        query_items = list(query)
        if query_items:
            separator = "&" if target.query else "?"
            url += separator + urlencode(query_items)

        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if authenticated:
            if not self.token:
                raise ApiError(
                    "Authentication is required. Run 'gridee auth login', pass --token, "
                    "or provide --email and a password."
                )
            request_headers.setdefault("Authorization", f"{self.token_type} {self.token}")

        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        request = Request(url, data=payload, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            raw = exc.read()
            message = _decode_response(raw, exc.headers.get("Content-Type", ""))
            if isinstance(message, dict):
                detail = message.get("message") or message.get("error") or json.dumps(message)
            else:
                detail = str(message).strip() or exc.reason
            raise ApiError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ApiError(f"Could not reach {url}: {exc.reason}") from exc
        return _decode_response(raw, content_type)

    def login(self, email: str, password: str) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/api/auth/login",
            body={"email": email, "password": password},
            authenticated=False,
        )
        if not isinstance(response, dict):
            raise ApiError("Login returned an unexpected non-object response.")
        token = response.get("token") or response.get("accessToken")
        if not isinstance(token, str) or not token:
            if response.get("mfaRequired"):
                raise ApiError("Login requires MFA; complete MFA in the official app, then pass a token.")
            raise ApiError("Login response did not contain a token.")
        self.token = token
        self.token_type = str(response.get("tokenType") or "Bearer")
        self.last_login_response = response
        return response


def _decode_response(raw: bytes, content_type: str) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def parse_pairs(values: Iterable[str], label: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise ApiError(f"{label} must use KEY=VALUE syntax: {value!r}")
        key, item = value.split("=", 1)
        if not key:
            raise ApiError(f"{label} key cannot be empty.")
        pairs.append((key, item))
    return pairs


def resolve_password(args: Any, *, required: bool) -> str | None:
    if getattr(args, "password_stdin", False):
        value = sys.stdin.readline().rstrip("\r\n")
    else:
        value = getattr(args, "password", None)
    if value:
        return value
    if required and sys.stdin.isatty():
        return getpass.getpass("Gridee password: ")
    if required:
        raise ApiError("A password is required; use the secure prompt, --password-stdin, or GRIDEE_PASSWORD.")
    return None


def authenticated_client(args: Any, *, allow_login: bool = True) -> tuple[ApiClient, SessionStore]:
    store = SessionStore(Path(args.session_file).expanduser())
    session = store.load()
    explicit_token = getattr(args, "token", None)
    requested_base = str(args.base_url).rstrip("/")
    saved_base = str(session.get("baseUrl") or requested_base).rstrip("/")
    same_origin = requested_base == saved_base
    client = ApiClient(
        args.base_url,
        token=explicit_token or (session.get("token") if same_origin else None),
        token_type=(getattr(args, "token_type", None) or (session.get("tokenType") if same_origin else None) or "Bearer"),
        timeout=args.api_timeout,
    )

    email = getattr(args, "email", None)
    if allow_login and email:
        response = client.login(email, resolve_password(args, required=True) or "")
        if not getattr(args, "no_save", False):
            store.save(
                {
                    "baseUrl": client.base_url.rstrip("/"),
                    "token": client.token,
                    "tokenType": client.token_type,
                    "email": email,
                    "user": response.get("user"),
                    "mfaRequired": response.get("mfaRequired"),
                    "profileComplete": response.get("profileComplete"),
                }
            )
    return client, store


def print_result(value: Any) -> None:
    if isinstance(value, (dict, list)) or value is None:
        print(json.dumps(value, indent=2))
    else:
        print(value)


def load_json_body(args: Any) -> Any:
    if getattr(args, "data_file", None):
        raw = Path(args.data_file).read_text(encoding="utf-8")
    elif getattr(args, "data", None) is not None:
        raw = args.data
    else:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(f"Request body is not valid JSON: {exc}") from exc


def run_auth(args: Any) -> int:
    if args.auth_command == "logout":
        store = SessionStore(Path(args.session_file).expanduser())
        print("Saved session removed." if store.clear() else "No saved session found.")
        return 0

    if args.auth_command == "login":
        if not args.email:
            raise ApiError("Email is required; pass --email or set GRIDEE_EMAIL.")
        client, store = authenticated_client(args)
        session = store.load() if not args.no_save else client.last_login_response
        result = {
            "authenticated": bool(client.token),
            "tokenType": client.token_type,
            "saved": not args.no_save,
            "sessionFile": str(store.path) if not args.no_save else None,
            "user": session.get("user"),
            "mfaRequired": session.get("mfaRequired"),
            "profileComplete": session.get("profileComplete"),
        }
        if args.show_token:
            result["token"] = client.token
        print_result(result)
        return 0

    client, store = authenticated_client(args, allow_login=False)
    session = store.load()
    result: dict[str, Any] = {
        "authenticated": bool(client.token),
        "baseUrl": client.base_url.rstrip("/"),
        "tokenType": client.token_type if client.token else None,
        "sessionFile": str(store.path),
        "savedEmail": session.get("email"),
    }
    if args.live and client.token:
        result["user"] = client.request("GET", "/api/oauth2/user")
    print_result(result)
    return 0


def extract_user_id(payload: Any) -> str | None:
    """Find a user identifier in common current-principal response wrappers."""
    if isinstance(payload, dict):
        for key in ("id", "userId", "user_id", "sub"):
            candidate = payload.get(key)
            if isinstance(candidate, (str, int)) and not isinstance(candidate, bool):
                value = str(candidate).strip()
                if value:
                    return value
        for key in ("user", "data", "principal", "profile", "account"):
            found = extract_user_id(payload.get(key))
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = extract_user_id(item)
            if found:
                return found
    return None


def resolve_user_id(client: ApiClient, requested: str | None = None) -> str:
    if requested is not None:
        value = requested.strip()
        if not value:
            raise ApiError("--user-id cannot be empty.")
        return value
    current = client.request("GET", "/api/oauth2/user")
    user_id = extract_user_id(current)
    if user_id is None:
        raise ApiError(
            "The current-user response did not contain an ID; pass --user-id explicitly."
        )
    return user_id


def run_api(args: Any) -> int:
    client, _ = authenticated_client(args)
    if args.api_command == "user":
        result = client.request("GET", "/api/oauth2/user")
    elif args.api_command == "parking-lots":
        result = client.request("GET", "/api/parking-lots")
    elif args.api_command == "wallet":
        user_id = resolve_user_id(client, args.user_id)
        path = f"/api/users/{quote(user_id, safe='')}/wallet"
        result = client.request("GET", path)
    elif args.api_command == "wallet-topup":
        if not math.isfinite(args.amount) or args.amount <= 0:
            raise ApiError("--amount must be a finite number greater than zero.")
        user_id = resolve_user_id(client, args.user_id)
        path = f"/api/users/{quote(user_id, safe='')}/wallet/topup"
        body = {"amount": args.amount}
        if args.execute:
            result = client.request("POST", path, body=body)
        else:
            result = {
                "dryRun": True,
                "method": "POST",
                "path": path,
                "body": body,
                "message": "Preview only; add --execute to send the server-controlled top-up request.",
            }
    else:
        query = parse_pairs(args.query, "--query")
        header_pairs = parse_pairs(args.header, "--header")
        headers = dict(header_pairs)
        result = client.request(
            args.method,
            args.path,
            body=load_json_body(args),
            query=query,
            headers=headers,
            authenticated=not args.anonymous,
        )
    print_result(result)
    return 0
