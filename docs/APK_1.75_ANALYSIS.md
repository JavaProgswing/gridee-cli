# Gridee 1.75 device APK analysis

Analyzed on 2026-10-07 from the installed `com.gridee.parking` package on the
authorized Android device connected over ADB.

## Captured build

- Version name: `1.75`
- Version code: `83`
- Installed update time reported by Android: `2026-10-07 12:27:52`
- Base APK SHA-256: `8b0e88ee0327c64a976441bb6584470b58755e54a97746e055c99888a9bec696`
- Installed APK set: `base.apk`, `split_config.arm64_v8a.apk`, and
  `split_config.xxxhdpi.apk`
- Retrofit interface after obfuscation: `mf.c`

The APK binaries and decompiled source are local analysis artifacts and are ignored
by Git. The versioned, non-secret route report is committed as
[`ENDPOINTS_1.75.md`](ENDPOINTS_1.75.md).

## Booking API changes

The v1.75 interface still declares both current-booking routes:

- `GET /api/bookings/{userId}/all`
- `GET /api/parking-lots/{lotId}/bookings/{userId}/all`

It adds paginated history routes with `status`, `page`, and `size` query parameters:

- `GET /api/bookings/{userId}/history/page`
- `GET /api/parking-lots/{lotId}/bookings/{userId}/history/page`

The app first calls the lot-scoped booking route when a lot is selected and falls
back to the global route only for HTTP `404`, `405`, or `501`. Its history screen uses
the new page routes and falls back to the legacy history collection when those status
codes indicate an older backend.

## Why `/all` failed in the Python client

The route was not removed. A controlled read-only test with a valid Firebase-exchange
session produced:

| Request identity | Result |
|---|---|
| aiohttp default Python user agent | `403 Security Restriction` |
| `X-App-Version` only | `403 Security Restriction` |
| `X-Device-Id` only | `403 Security Restriction` |
| `User-Agent: okhttp/4.12.0` | HTTP 200 |
| Full observed Android transport headers | HTTP 200 |

The v1.75 APK's network interceptor sends `User-Agent: okhttp/4.12.0`,
`X-App-Version: android/1.75 (83)`, an `X-Device-Id` when Android supplies one, and an
`X-Firebase-AppCheck` token when App Check is enabled and a token is available. The
CLI now sends the non-secret OkHttp user agent and app version automatically; a device
ID remains optional. It does not fabricate or bypass Firebase App Check.

After the fix, a fresh client session successfully read both:

- `/api/bookings/{currentUserId}/all` — HTTP 200, normal Spring page envelope
- `/api/bookings/{currentUserId}/history/page?page=0&size=5` — HTTP 200, v1.75
  `{items, counts, hasMore, page, size}` envelope

No booking, cancellation, payment, wallet, or other write endpoint was called during
this verification.

## CLI behavior changed

- `gridee_aiohttp.GrideeClient` now applies the observed Android transport identity to
  login and authenticated calls, so both `gridee_wallet.py` and
  `gridee_booking_service.py` inherit the fix without cyclic imports.
- Booking monitoring still uses `/all` for duplicate-safe current-booking recovery,
  because v1.75 itself retains that route and it succeeds with the correct transport
  identity.
- When a known booking disappears from its detail route, lookup now tries the new
  paginated history endpoint before legacy history/current collections.
- `tools/pull_gridee_apk.py` pulls every installed split from an authorized ADB device,
  records package metadata and SHA-256 hashes, and optionally launches an endpoint
  audit.
- `tools/gridee_apk_audit.py` now understands both unobfuscated Retrofit annotations
  and the v1.75 obfuscated aliases, with a JADX-source fallback for constrained
  Windows/JVM environments.
