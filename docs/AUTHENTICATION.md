# Gridee 1.71 authentication and HTTP headers

Source: static inspection of `JwtAuthInterceptor`, `UnauthorizedInterceptor`, `ApiService`, and the request models in the installed APK (`versionName=1.71`, `versionCode=72`).

## Required authentication header

For authenticated API calls, the app uses:

```http
Authorization: Bearer <JWT access token>
```

The OkHttp interceptor behaves as follows:

1. If a request already has an `Authorization` header, it leaves the request unchanged.
2. Otherwise, for a non-public path, it asks the app's token manager for a valid bearer token.
3. If one is available, it adds the `Authorization` header.
4. If no valid token is available, it still sends the request without the header; the server decides whether to reject it.
5. A `401 Unauthorized` response to a request that carried authentication is treated as a dead session.

No fixed API-key header was found in the app client.

## Paths excluded from automatic JWT attachment

The interceptor marks these paths as public/authentication paths:

```text
/api/auth/login
/api/auth/register
/api/auth/google
/api/auth/firebase/exchange
/api/users/login
/api/users/social-signin
/api/otp/generate
/api/otp/validate
```

The last four are legacy/compatibility exclusions and are not all declared by the current `ApiService` interface.

Every other route in [API_REFERENCE.md](API_REFERENCE.md) is eligible for automatic JWT attachment. This includes `api/config/all`; the interceptor does not classify it as public, although the server may independently allow anonymous access.

## Endpoint-specific header declarations

Most `ApiService` methods rely entirely on the global JWT interceptor. Two methods also declare the header explicitly in their Retrofit signature:

| Method and route | Explicit header |
|---|---|
| `POST api/notifications/tokens` | `Authorization` |
| `DELETE api/notifications/tokens` | `Authorization` |

Those methods still use the same bearer-token value; this is not a second credential scheme.

## Content headers

- Retrofit/Gson supplies JSON request serialization for methods with `@Body`; the effective content type is normally `application/json`.
- GET methods and POST methods without a body do not require a manually constructed JSON content header.
- No app-defined mandatory `X-API-Key`, custom device-signature, CSRF, or static secret header was observed in `ApiService`/`ApiClient`.
- Normal transport headers added by OkHttp or the Android networking stack are implementation details, not authentication credentials.

## Legitimate token acquisition

The supported way to obtain a session is to authenticate normally. The declared login/register/Google/Firebase-exchange methods return `AuthResponse`, which contains `token`, `tokenType`, user/session flags, and the user profile. The installed app saves that response internally and its interceptor attaches it automatically on later calls.

For this project's UI automation, no token handling is necessary: Gridee remains responsible for login, secure storage, expiration, and header attachment.

If developing an authorized API client, use an account and server environment you are permitted to test, authenticate through the supported endpoint, keep the returned token in protected application storage, and pass it using the server-provided `tokenType` (observed client fallback: `Bearer`). Do not log it, commit it, paste it into command history, or place it in this repository.

## Merged CLI authentication modes

The unified CLI now supports authorized API calls in three ways:

1. `gridee auth login --email ADDRESS` performs a live login and securely prompts for the password.
2. `--email` with `--password`, `--password-stdin`, or `GRIDEE_PASSWORD` performs an explicit credential login for that command.
3. `--token` or `GRIDEE_TOKEN` accepts an already-authorized bearer token.

A successful login can save only the returned token and non-secret response metadata in the configured local session file; the password is never saved. Saved tokens are origin-bound and are not sent when `--base-url` points elsewhere. `gridee api request` exposes GET, POST, PUT, PATCH, and DELETE with JSON bodies and query/header options, so the entire documented route inventory is callable without hard-coding every endpoint.

