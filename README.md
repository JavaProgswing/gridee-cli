# Gridee CLI

A unified toolkit for authorized Gridee automation. It combines:

- Android ADB/UIAutomator inspection and control
- rewarded-ad Wallet automation with notification-based credit verification
- parking-booking preparation and optional submission through the official Android UI
- live HTTP API authentication with email/password, bearer-token, and saved-session modes
- a generic API request command covering every route in the endpoint inventory
- an optional on-device Android scheduler that can fire when the computer is disconnected

Use only your own account, device, and bookings. The CLI does not bypass MFA, a secure device lock, server-side booking rules, or TLS controls.

## Requirements

- Python 3.10+
- Android platform-tools (`adb`) on `PATH` for device commands
- a USB-debugging-authorized Android device with Gridee installed and logged in
- for the optional scheduler APK: Android SDK platform 35, build-tools 35.0.0, a JDK, and the normal Android debug keystore

The core Python CLI has no third-party runtime dependencies. The optional standalone async client uses `aiohttp`; tests use `pytest`.

## Quick start

```powershell
python .\gridee.py --help
python .\gridee.py devices
python .\gridee.py info
python .\gridee.py balance
```

If `adb` is not on `PATH`, pass `--adb C:\path\to\adb.exe` or set `GRIDEE_ADB`. Use `--device SERIAL` or `GRIDEE_DEVICE` when more than one device is connected.

## Wallet and device automation

```powershell
python .\gridee.py wallet
python .\gridee.py reward                 # watch one rewarded ad
python .\gridee.py reward --earn 200      # add 200 points
python .\gridee.py reward --target 2000   # stop at a final balance
python .\gridee.py monitor --until-change
python .\gridee.py screenshot --name before-booking
python .\gridee.py dump --list
python .\gridee.py inspect
```

The reward flow gates taps on Gridee being foreground, backs out of accidental Play Store/browser screens, and confirms credits from Android's Wallet Updated notifications.

## Booking through the Android UI

Booking is a dry run by default: it selects the best available fuzzy venue match, configures the time window, and stops before confirmation.

```powershell
python .\gridee.py booking
python .\gridee.py booking --venue "TP Avenue" --start 09:15 --end 16:30
python .\gridee.py booking --date 2026-08-21 --execute
```

Defaults are venue `Tech Park Avenue`, opening time `05:00`, and booking window `08:00`-`17:00`. A same-day late run starts at the next five-minute boundary after the configured buffer; after the window ends, an implicit date moves to the next day.

The former entry point remains available:

```powershell
python .\gridee_booking.py --venue "TP Avenue" --execute
```

## Live API authentication

The default API origin is `https://gridee.onrender.com`. Login first tries `POST /api/auth/login`. On a 401/404 it follows the Android app's fallback: Firebase email/password sign-in, verified-email lookup, then `POST /api/auth/firebase/exchange`. It saves the returned Gridee token and attaches `Authorization: Bearer <token>` to authenticated calls.

### Secure interactive login

```powershell
# Prompts locally for both email and password, then saves the returned token.
python .\gridee.py auth login

# Or provide only the non-secret email and prompt just for the password.
python .\gridee.py auth login --email "you@example.com"
python .\gridee.py auth status --live
```

The first command securely prompts for the password. Only the final Gridee token and non-secret session metadata are saved under `%LOCALAPPDATA%\gridee-cli\session.json`; the password, Firebase ID token, and Firebase refresh token are not saved. A saved token is only reused with the API origin that issued it.

### Manually supplied credentials

```powershell
# Environment variables avoid putting the password in shell history.
$env:GRIDEE_EMAIL = "you@example.com"
$env:GRIDEE_PASSWORD = Read-Host "Gridee password"
python .\gridee.py api user
Remove-Item Env:GRIDEE_PASSWORD

# Noninteractive input is also supported.
$env:GRIDEE_PASSWORD | python .\gridee.py auth login --email "you@example.com" --password-stdin

# A literal flag works but can be visible in command history/process listings.
python .\gridee.py auth login --email "you@example.com" --password "YOUR_PASSWORD"
```

Use `--no-save` for a one-process login. Use `--show-token` only when you explicitly need to inspect/copy the token.

### Existing bearer token

```powershell
python .\gridee.py api user --token "YOUR_TOKEN"

# Or keep it out of the command line.
$env:GRIDEE_TOKEN = "YOUR_TOKEN"
python .\gridee.py api parking-lots
Remove-Item Env:GRIDEE_TOKEN
```

If the server reports `mfaRequired` without issuing a token, complete MFA in the official app and then provide an authorized bearer token. The CLI does not pull private app storage or bypass MFA.

### Session management

```powershell
python .\gridee.py auth status
python .\gridee.py auth status --live
python .\gridee.py auth logout
```

Override the origin/session path with `GRIDEE_BASE_URL`, `GRIDEE_SESSION_FILE`, `--base-url`, or `--session-file`.

## Standalone aiohttp client

[`gridee_aiohttp.py`](gridee_aiohttp.py) is now a small reusable async client containing
only app-compatible authentication, an authenticated session, and generic API requests.
Install its optional dependency:

```powershell
python -m pip install -r .\requirements-aiohttp.txt
```

Run it directly to authenticate and fetch the current user:

```powershell
Copy-Item .\.env.example .\.env
notepad .\.env
python .\gridee_aiohttp.py
```

Or import the client and make multiple calls on the same session:

```python
async with GrideeClient(email, password) as client:
    me = await client.request("GET", "/api/oauth2/user")
    lots = await client.request("GET", "/api/parking-lots")
```

Values already present in the process environment take precedence over `.env`. If no
password is configured, direct use prompts for it locally. Use the email without a
backslash before `@`. The real `.env` is ignored by Git.

## Daily 05:00 booking service

[`gridee_booking_service.py`](gridee_booking_service.py) is a separate long-running
worker. It submits the saved booking through
`POST /api/bookings/{userId}/create` once per local calendar day at `05:00`.
Create its private configuration:

```powershell
python .\gridee_booking_service.py --init
python .\gridee_booking_service.py --setup
```

`--setup` authenticates locally and detects registered vehicles, parking lots, and
available spots. A single result is selected automatically; multiple results are shown
as numbered choices, and a missing result falls back to manual entry. The choices are
saved as `spotId`, `lotId`, and `vehicleNumber`. Starting the service from an
interactive console also launches this setup automatically when those values are missing.
Existing partial configuration files are deep-merged with safe defaults, so missing
booking times and retry options are restored without replacing a selected user, lot,
spot, or vehicle.

The default saved times are `{date}T08:00:00{offset}` through
`{date}T17:00:00{offset}`. `{date}` is replaced with the scheduled local date,
and `{offset}` with the local UTC offset (for example, `+05:30`). This matches the
Android app/API format. `{tomorrow}` is also supported. Older saved times without an
offset are upgraded automatically before each request.

Validate the rendered request without booking:

```powershell
python .\gridee_booking_service.py --once --dry-run
```

Then configure `.env` and start the service loop:

```powershell
Copy-Item .\.env.example .\.env
notepad .\.env
python .\gridee_booking_service.py
```

For Pterodactyl, upload the completed `.env` through **Files**, set **APP PY FILE**
to `gridee_booking_service.py`, and set **REQUIREMENTS FILE** to
`requirements-aiohttp.txt`. If the egg only exposes **Additional Python Packages**,
enter `aiohttp python-dotenv`. No custom Pterodactyl environment variables are required.

The normal service command sends the booking automatically without an interactive
confirmation. It reloads `booking_service.json` before each attempt, accepts starts
up to `graceMinutes` after 05:00, and writes `booking_service.state.json` before
submitting so a restart cannot submit the same day's booking twice. Both local files
are ignored by Git. After a successful booking, the worker checks that exact booking
every five seconds. Once the booking is actually in progress (`ACTIVE`,
`actualCheckInTime`, or `qrCodeScanned`), monitoring stops and it will never rebook
that booking. A cancellation by itself also does not trigger a replacement. The
worker first requires a completed wallet refund transaction whose `bookingId`
matches the cancelled booking, which distinguishes the automatic cancellation flow.
It then creates a replacement immediately and monitors the replacement. Failed
replacement requests retry every five seconds. This resumes safely after a worker
restart.

On startup after `runAt` and before `checkOutTime`, the worker queries
`GET /api/bookings/{userId}/all` even when the local state file is missing. A
live booking for that day is adopted and monitored without another create request,
even if its lot, spot, or vehicle differs from the saved entry. If the API confirms
that no current booking exists, the worker creates one, saves its ID, and starts
monitoring it. A `409 Booking conflict` triggers another current-booking lookup and
adoption. If the server reports a conflict but omits the existing booking ID, create
attempts are disabled for that day instead of looping every five seconds. If the
initial lookup itself fails, the worker does not guess or submit blindly.
If a saved booking ID is absent from both the live and history endpoints, its status
is `MISSING`, not `CANCELLED`. The stale ID is discarded immediately and the worker
runs the same lookup-before-create recovery on the next five-second cycle; it does
not enter the manual-cancellation refund timeout. State produced by the older behavior
with `status: cancelled-no-refund` and `bookingStatus: MISSING` is migrated into this
recovery path automatically on restart.

To change accounts, keep `"userId": "current"` and replace `GRIDEE_EMAIL` and
`GRIDEE_PASSWORD` in `.env`. State written by this version is bound to the resolved
user ID, so a changed authenticated account discards the previous account's tracked
booking and runs safe recovery for the new account. Delete an older
`booking_service.state.json` once if it was created before account binding was added.

To change `spotId`, `lotId`, or `vehicleNumber`, stop the worker, make sure the old
booking is no longer active, update `booking_service.json` (or run `--setup`), remove
`booking_service.state.json`, and restart. Invalid user IDs prevent the current-list
check and therefore never cause a blind create. Invalid lot, spot, or vehicle values
are rejected by the booking API and remain visible in the state/error log; correct
the values or rerun `--setup`, which detects values available to the authenticated
account.

The retry behavior is configured in `booking_service.json`:

```json
"rebook": {
  "enabled": true,
  "pollSeconds": 5,
  "retrySeconds": 5,
  "refundWaitSeconds": 120,
  "lateStartBufferMinutes": 5
}
```

Monitoring continues until the booking starts or that day's configured
`checkOutTime`. If a replacement is needed after the original `checkInTime`, its
start is advanced to the next five-minute boundary after
`lateStartBufferMinutes`; this avoids sending a start time in the past. A manual
cancellation without a matching completed refund is never rebooked. After upgrading
from the old timestamp format, a same-day `Invalid date format` failure is retried
exactly once on startup, even after the normal grace period. A cancelled booking
without a matching refund leaves the refund-wait loop after `refundWaitSeconds`, is
saved as `cancelled-no-refund`, and proceeds to the normal next-day schedule. Use
`--once` without `--dry-run` only to submit immediately; `--once` does not start the
monitor.

## API commands

Convenience commands mirror the supplied PowerShell examples:

```powershell
python .\gridee.py api user
python .\gridee.py api parking-lots
```

### Add credit to the currently authenticated account

This placeholder-free PowerShell flow prompts for the email, password, and amount. The CLI resolves the current account ID internally:

```powershell
Set-Location "C:\Users\yashasvi\Downloads\gridee_cli"
$email = (Read-Host "Gridee email").Trim()
[double]$amount = Read-Host "Top-up amount"
if (-not $email -or $amount -le 0) { throw "Email and a positive amount are required" }

# 1. Authenticate. The CLI prompts for the password and saves only the returned session.
python .\gridee.py auth login --email "$email"
if ($LASTEXITCODE -ne 0) { throw "Gridee login failed" }
python .\gridee.py auth status --live
if ($LASTEXITCODE -ne 0) { throw "Saved Gridee session is not valid" }

# 2. Confirm that the CLI can resolve the current account and read its wallet.
python .\gridee.py api wallet
if ($LASTEXITCODE -ne 0) { throw "Could not resolve the current account wallet" }

# 3. Preview only. This validates the command but sends no write request.
python .\gridee.py api wallet-topup --amount $amount

# 4. Resolve the current user and send the authenticated top-up request.
$topup = python .\gridee.py api wallet-topup `
    --amount $amount `
    --execute | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Wallet top-up initiation failed" }
$topup | ConvertTo-Json -Depth 10

# 5. Read the resulting wallet balance/details.
python .\gridee.py api wallet
if ($LASTEXITCODE -ne 0) { throw "Could not read the wallet after top-up" }

# 6. If the response returned an order ID, inspect payment/credit status.
$orderId = @($topup.orderId, $topup.data.orderId) |
    Where-Object { $null -ne $_ -and "$($_)".Trim() } |
    Select-Object -First 1
if ($orderId) {
    python .\gridee.py api request "/api/payments/status/$orderId"
}
```

`wallet-topup` invokes the authenticated, server-controlled top-up initiation route. It cannot directly force credit or bypass payment, authorization, configured amount limits, or other server validation. If the returned order requires payment, finish it through the official Gridee/payment-gateway flow and rerun the wallet/status commands.

Every documented endpoint is supported through the generic request command:

```powershell
# GET with query parameters
python .\gridee.py api request /api/bookings/my-bookings --query active=true

# POST a JSON object
python .\gridee.py api request /api/notifications/tokens `
  --method POST `
  --data '{"token":"FCM_TOKEN","platform":"android"}'

# Read a larger JSON body from disk
python .\gridee.py api request /api/bookings --method POST --data-file .\booking.json

# Explicit anonymous/public request
python .\gridee.py api request /api/auth/login --method POST --anonymous `
  --data '{"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}'
```

Repeat `--query KEY=VALUE` or `--header KEY=VALUE` as needed. Supported methods are GET, POST, PUT, PATCH, and DELETE. Prefer the dedicated `auth login` command for credentials because it handles tokens without printing them.

The current APK-derived endpoint inventory is:

- [Gridee 1.73 generated endpoint audit](docs/ENDPOINTS_1.73.md)

The earlier hand-written v1.71 references are retained for context:

- [Complete API reference](docs/API_REFERENCE.md)
- [Endpoint inventory](docs/API_ENDPOINTS_COMPLETE.md)
- [Authentication/header notes](docs/AUTHENTICATION.md)
- [Earlier endpoint notes](docs/ENDPOINTS.md)

## On-device booking scheduler

The Android helper uses an exact alarm and an accessibility service to drive the normal Gridee UI. It is dry-run by default, supports one-shot or daily schedules, and cannot bypass a secure PIN.

```powershell
python .\gridee.py scheduler build
python .\gridee.py scheduler install
python .\gridee.py scheduler enable

# After enabling "Gridee booking scheduler" in Android accessibility settings:
python .\gridee.py scheduler schedule `
  --at 2026-08-21T04:59:55 `
  --venue "TP Avenue" `
  --start 08:00 `
  --end 17:00

# Repeat at the same local time every day and press final confirmation.
python .\gridee.py scheduler schedule `
  --at 2026-08-21T05:00:00 `
  --daily `
  --venue "Tech Park Avenue" `
  --start 08:00 `
  --end 17:00 `
  --execute

python .\gridee.py scheduler status
python .\gridee.py scheduler cancel

# Launch a safe dry-run now without changing the saved alarm.
python .\gridee.py scheduler simulate
```

Add `--execute` only when the helper should press final confirmation. With `--daily`, the helper re-arms for the same local time on the next day after each alarm, including across device reboots; do not combine it with a fixed `--date`. `scheduler simulate` launches the same APK flow immediately in dry-run mode, never presses final confirmation, and preserves the pending alarm. Source lives in `android-helper/`; the build output is `android-helper/build/gridee-scheduler-debug.apk`.

## APK analysis notes

The installed-app APK is intentionally not committed to this merged repository. If you
are authorized to inspect your local copy, place it under `analysis/` (ignored by Git).
Generate a versioned endpoint report with:

```powershell
python .\tools\gridee_apk_audit.py .\analysis\gridee-1.73-base.apk `
  --output .\docs\ENDPOINTS_1.73.md

python .\tools\gridee_apk_audit.py .\analysis\gridee-1.73-base.apk `
  --format json --output .\analysis\gridee-1.73-endpoints.json
```

The tool reads the manifest version and extracts Retrofit method/path/query/body
annotations from `ApiService`, merges overloads into unique HTTP endpoints, and
decompiles referenced request/response models into JSON field patterns. The Markdown
report is human-readable; the JSON report embeds request and response patterns directly
on every endpoint.

The captured non-secret UI hierarchy used for parser regression testing remains at `analysis/gridee-booking-home.xml`.

## Configuration

ADB defaults can be supplied with `GRIDEE_DEVICE`, `GRIDEE_PACKAGE`, `GRIDEE_ACTIVITY`, `GRIDEE_ADB`, and `GRIDEE_OUTPUT`. API defaults use `GRIDEE_BASE_URL`, `GRIDEE_SESSION_FILE`, `GRIDEE_TOKEN`, `GRIDEE_TOKEN_TYPE`, `GRIDEE_EMAIL`, `GRIDEE_PASSWORD`, and `GRIDEE_FIREBASE_API_KEY`.

Run command-specific help for the complete option list:

```powershell
python .\gridee.py reward --help
python .\gridee.py booking --help
python .\gridee.py auth login --help
python .\gridee.py api request --help
python .\gridee.py scheduler --help
```

## Tests

```powershell
python -m pytest -q
```

Device-free tests cover CLI parsing, API authentication/header behavior, session storage, booking schedule logic, imported UI fixtures, Wallet parsing, activity classification, and notification handling.

## License

MIT - see [LICENSE](LICENSE).
