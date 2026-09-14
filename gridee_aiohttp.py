from __future__ import annotations

import asyncio
import getpass
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False, interpolate=False)


BASE_URL = "https://gridee.onrender.com"
FIREBASE_KEY = "AIzaSyDN63teqDI3fvPQRY2NUyGbmiCklbLgkls"
FIREBASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts:"


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


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
            raise ApiError(
                f"{method.upper()} {endpoint} -> HTTP {response.status}: {error}",
                response.status,
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
    ) -> None:
        self.email = email.strip().lower()
        if "\\@" in self.email:
            raise ApiError(r"Use name@example.com, not name\@example.com.")
        self.password = password
        self.base_url = base_url.rstrip("/") + "/"
        self.firebase_key = firebase_key
        self.session: aiohttp.ClientSession | None = None
        self.auth_method = ""
        self.user: dict[str, Any] = {}

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
        )
        try:
            await self.login()
        except Exception:
            await self.session.close()
            raise
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.session:
            await self.session.close()

    async def login(self) -> None:
        assert self.session
        password = self.password
        self.password = ""
        try:
            auth = await _json(
                self.session,
                "POST",
                self.url("/api/auth/login"),
                json={"email": self.email, "password": password},
            )
            self.auth_method = "direct"
        except ApiError as error:
            if error.status not in {401, 404}:
                raise
            params = {"key": self.firebase_key}
            firebase = await _json(
                self.session,
                "POST",
                FIREBASE_URL + "signInWithPassword",
                params=params,
                json={"email": self.email, "password": password, "returnSecureToken": True},
            )
            token = firebase["idToken"]
            account = await _json(
                self.session,
                "POST",
                FIREBASE_URL + "lookup",
                params=params,
                json={"idToken": token},
            )
            if not account.get("users") or account["users"][0].get("emailVerified") is not True:
                raise ApiError("Firebase email is not verified.")
            auth = await _json(
                self.session,
                "POST",
                self.url("/api/auth/firebase/exchange"),
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
        return await _json(self.session, method.upper(), self.url(path), **kwargs)


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
