from __future__ import annotations

import asyncio
import getpass
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from gridee_aiohttp import ApiError, FIREBASE_KEY, GrideeClient
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False, interpolate=False)

def find_user_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("id", "userId", "user_id", "sub"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        for key in ("user", "data", "principal", "profile", "account"):
            found = find_user_id(value.get(key))
            if found:
                return found
    return None


def saved_user_id(path: Path | None = None) -> str | None:
    configured = os.getenv("GRIDEE_USER_ID")
    if configured:
        return configured.strip()
    path = path or Path(__file__).with_name("booking_service.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("userId")
    except (FileNotFoundError, OSError, json.JSONDecodeError, AttributeError):
        return None
    return str(value) if value and str(value).lower() != "current" else None


async def resolve_user_id(client: GrideeClient, user_id: str | None = None) -> str:
    user_id = user_id or find_user_id(client.user)
    if not user_id:
        try:
            user_id = find_user_id(await client.request("GET", "/api/oauth2/user"))
        except ApiError as exc:
            raise ApiError(
                "Could not resolve the current user ID. Set GRIDEE_USER_ID in .env "
                "or save userId in booking_service.json. "
                f"The profile endpoint also failed: {exc}",
                exc.status,
            ) from exc
    if not user_id:
        raise ApiError("Could not resolve the current user ID.")
    return user_id


def find_balance(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("balance", "walletBalance", "availableBalance", "credits", "points"):
            try:
                if value.get(key) not in (None, ""):
                    return float(value[key])
            except (TypeError, ValueError):
                pass
        for item in value.values():
            found = find_balance(item)
            if found is not None:
                return found
    return None


async def fetch_wallet_details(
    client: GrideeClient, user_id: str | None = None
) -> tuple[str, Any]:
    user_id = await resolve_user_id(client, user_id)
    root = f"/api/users/{quote(user_id, safe='')}/wallet"
    return user_id, await client.request("GET", root)


async def fetch_wallet(
    client: GrideeClient, user_id: str | None = None
) -> dict[str, Any]:
    user_id = await resolve_user_id(client, user_id)
    root = f"/api/users/{quote(user_id, safe='')}/wallet"
    wallet, transactions = await asyncio.gather(
        client.request("GET", root),
        client.request("GET", root + "/transactions"),
    )
    return {
        "userId": user_id,
        "wallet": wallet,
        "transactions": transactions,
    }

async def top_up_wallet(client: GrideeClient, user_id: str, amount: int) -> dict[str, Any]:
    user_id = await resolve_user_id(client, user_id)
    root = f"/api/users/{quote(user_id, safe='')}/wallet/topup"
    response = await client.request("POST", root, json={"amount": amount})
    return response

async def main() -> None:
    email = os.getenv("GRIDEE_EMAIL") or input("Gridee email: ")
    password = os.getenv("GRIDEE_PASSWORD") or getpass.getpass("Gridee password: ")
    async with GrideeClient(
        email,
        password,
        base_url=os.getenv("GRIDEE_BASE_URL", "https://gridee.onrender.com"),
        firebase_key=os.getenv("GRIDEE_FIREBASE_API_KEY", FIREBASE_KEY),
    ) as client:
        target = 1500
        wallet = await fetch_wallet(client, saved_user_id())
        wallet = wallet.get("wallet", {})
        print(f"Current wallet balance: {wallet.get('balance', 0)}, target: {target}")
        while wallet.get("balance", 0) < target:
            wallet = await top_up_wallet(client, saved_user_id(), 10)
        

    


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ApiError, aiohttp.ClientError) as exc:
        raise SystemExit(f"[!] {exc}") from exc
