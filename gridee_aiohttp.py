from __future__ import annotations

import asyncio
import getpass
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False, interpolate=False)


BASE_URL = "https://gridee.onrender.com"
FIREBASE_KEY = "AIzaSyDN63teqDI3fvPQRY2NUyGbmiCklbLgkls"
FIREBASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts:"
APP_VERSION = "android/1.75 (83)"
APP_USER_AGENT = "okhttp/4.12.0"


class ApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status: int = 0,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _number_from_env(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _header(headers: Any, name: str) -> str | None:
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is not None:
            return str(value)
        value = headers.get(name.lower())
        if value is not None:
            return str(value)
    return None


def retry_after_seconds(headers: Any, data: Any, now: datetime | None = None) -> float | None:
    """Parse standard and commonly deployed rate-limit reset signals."""
    value = _header(headers, "Retry-After")
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return max(0.0, (target - (now or datetime.now(timezone.utc))).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass

    for name in ("RateLimit-Reset", "X-RateLimit-Reset"):
        value = _header(headers, name)
        if not value:
            continue
        try:
            numeric = float(value)
        except ValueError:
            continue
        current = (now or datetime.now(timezone.utc)).timestamp()
        return max(0.0, numeric - current if numeric > current + 1 else numeric)

    if isinstance(data, dict):
        candidates = [data]
        if isinstance(data.get("error"), dict):
            candidates.append(data["error"])
        for candidate in candidates:
            for name in ("retryAfter", "retryAfterSeconds", "retry_after"):
                try:
                    if candidate.get(name) is not None:
                        return max(0.0, float(candidate[name]))
                except (TypeError, ValueError):
                    continue
    return None


async def _json(session: aiohttp.ClientSession, method: str, url: str, **kwargs: Any) -> Any:
    async with session.request(method, url, **kwargs) as response:
        text = await response.text()
        try:
            data = json.loads(text) if text else None
        except json.JSONDecodeError:
            data = text
        if response.status >= 400:
            error = data.get("error", data) if isinstance(data, dict) else data
            if isinstance(error, dict):
                error = error.get("message") or error.get("status") or error
            endpoint = urlsplit(url).path
            retry_after = retry_after_seconds(
                getattr(response, "headers", {}), data
            ) if response.status == 429 else None
            suffix = (
                f"; retry after {retry_after:g}s"
                if retry_after is not None
                else ""
            )
            raise ApiError(
                f"{method.upper()} {endpoint} -> HTTP {response.status}: {error}{suffix}",
                response.status,
                retry_after,
            )
        return data


class GrideeClient:
    """Authenticated aiohttp client using the same fallback as the Android app."""

    def __init__(
        self,
        email: str,
        password: str,
        base_url: str = BASE_URL,
        firebase_key: str = FIREBASE_KEY,
        app_version: str | None = None,
        device_id: str | None = None,
        min_request_interval: float | None = None,
        rate_limit_retries: int | None = None,
        rate_limit_base_seconds: float | None = None,
        rate_limit_max_seconds: float | None = None,
    ) -> None:
        self.email = email.strip().lower()
        if "\\@" in self.email:
            raise ApiError(r"Use name@example.com, not name\@example.com.")
        self.password = password
        self.base_url = base_url.rstrip("/") + "/"
        self.firebase_key = firebase_key
        self.app_version = app_version or os.getenv("GRIDEE_APP_VERSION") or APP_VERSION
        self.device_id = device_id or os.getenv("GRIDEE_DEVICE_ID")
        self.min_request_interval = (
            max(0.0, min_request_interval)
            if min_request_interval is not None
            else _number_from_env("GRIDEE_MIN_REQUEST_INTERVAL_SECONDS", 1.0)
        )
        self.rate_limit_retries = (
            max(0, rate_limit_retries)
            if rate_limit_retries is not None
            else int(_number_from_env("GRIDEE_RATE_LIMIT_RETRIES", 4, 0))
        )
        self.rate_limit_base_seconds = (
            max(1.0, rate_limit_base_seconds)
            if rate_limit_base_seconds is not None
            else _number_from_env("GRIDEE_RATE_LIMIT_BASE_SECONDS", 15.0, 1.0)
        )
        self.rate_limit_max_seconds = (
            max(self.rate_limit_base_seconds, rate_limit_max_seconds)
            if rate_limit_max_seconds is not None
            else max(
                self.rate_limit_base_seconds,
                _number_from_env("GRIDEE_RATE_LIMIT_MAX_SECONDS", 300.0, 1.0),
            )
        )
        self.session: aiohttp.ClientSession | None = None
        self.auth_method = ""
        self.user: dict[str, Any] = {}
        self._request_lock: asyncio.Lock | None = None
        self._next_request_at = 0.0
        self._rate_limited_until = 0.0

    def url(self, path: str) -> str:
        url = urljoin(self.base_url, path.lstrip("/"))
        base, target = urlsplit(self.base_url), urlsplit(url)
        if (base.scheme, base.netloc) != (target.scheme, target.netloc):
            raise ApiError("Refusing to send authentication outside the Gridee API.")
        return url

    async def __aenter__(self) -> "GrideeClient":
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
            headers=self.app_headers(),
        )
        self._request_lock = asyncio.Lock()
        try:
            await self.login()
        except Exception:
            await self.session.close()
            raise
        return self

    def app_headers(self) -> dict[str, str]:
        """Return the non-secret transport headers used by Gridee's Android client."""
        headers = {
            "User-Agent": os.getenv("GRIDEE_USER_AGENT") or APP_USER_AGENT,
            "X-App-Version": self.app_version,
        }
        if self.device_id:
            headers["X-Device-Id"] = self.device_id
        return headers

    async def __aexit__(self, *_: object) -> None:
        if self.session:
            await self.session.close()

    async def login(self) -> None:
        assert self.session
        password = self.password
        self.password = ""
        try:
            auth = await self._request_json(
                "POST",
                self.url("/api/auth/login"),
                retry_rate_limit=True,
                json={"email": self.email, "password": password},
            )
            self.auth_method = "direct"
        except ApiError as error:
            if error.status not in {401, 404}:
                raise
            params = {"key": self.firebase_key}
            firebase = await self._request_json(
                "POST",
                FIREBASE_URL + "signInWithPassword",
                retry_rate_limit=True,
                params=params,
                json={"email": self.email, "password": password, "returnSecureToken": True},
            )
            token = firebase["idToken"]
            account = await self._request_json(
                "POST",
                FIREBASE_URL + "lookup",
                retry_rate_limit=True,
                params=params,
                json={"idToken": token},
            )
            if not account.get("users") or account["users"][0].get("emailVerified") is not True:
                raise ApiError("Firebase email is not verified.")
            auth = await self._request_json(
                "POST",
                self.url("/api/auth/firebase/exchange"),
                retry_rate_limit=True,
                json={"idToken": token},
            )
            self.auth_method = "firebase"

        token = auth.get("token") or auth.get("accessToken")
        if not token:
            raise ApiError("Gridee login did not return a token.")
        self.user = auth.get("user") if isinstance(auth.get("user"), dict) else {}
        self.session.headers["Authorization"] = f"{auth.get('tokenType') or 'Bearer'} {token}"

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.session:
            raise ApiError("Use GrideeClient inside 'async with'.")
        method = method.upper()
        return await self._request_json(
            method,
            self.url(path),
            retry_rate_limit=method in {"GET", "HEAD", "OPTIONS"},
            **kwargs,
        )

    async def _wait_for_request_slot(self) -> None:
        if self._request_lock is None:
            self._request_lock = asyncio.Lock()
        async with self._request_lock:
            now = time.monotonic()
            delay = max(self._next_request_at, self._rate_limited_until) - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = time.monotonic() + self.min_request_interval

    def _rate_limit_delay(self, error: ApiError, attempt: int) -> float:
        if error.retry_after is not None:
            return max(1.0, error.retry_after)
        return min(
            self.rate_limit_max_seconds,
            self.rate_limit_base_seconds * (2**attempt),
        )

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        retry_rate_limit: bool,
        **kwargs: Any,
    ) -> Any:
        if not self.session:
            raise ApiError("Use GrideeClient inside 'async with'.")
        attempts = self.rate_limit_retries if retry_rate_limit else 0
        for attempt in range(attempts + 1):
            await self._wait_for_request_slot()
            try:
                return await _json(self.session, method, url, **kwargs)
            except ApiError as error:
                if error.status != 429:
                    raise
                delay = self._rate_limit_delay(error, attempt)
                error.retry_after = delay
                self._rate_limited_until = max(
                    self._rate_limited_until,
                    time.monotonic() + delay,
                )
                if attempt >= attempts:
                    raise
        raise AssertionError("unreachable")


async def main() -> None:
    email = os.getenv("GRIDEE_EMAIL") or input("Gridee email: ")
    password = os.getenv("GRIDEE_PASSWORD") or getpass.getpass("Gridee password: ")
    async with GrideeClient(email, password) as client:
        print(json.dumps(await client.request("GET", "/api/oauth2/user"), indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ApiError, aiohttp.ClientError) as exc:
        raise SystemExit(f"[!] {exc}") from exc
