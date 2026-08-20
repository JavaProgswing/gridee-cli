# Gridee CLI

A unified, standard-library-only toolkit for authorized Gridee automation. It combines:

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

The Python CLI has no third-party runtime dependencies. Tests use `pytest`.

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

The default API origin is `https://gridee.onrender.com`. Login sends JSON to `POST /api/auth/login`, reads the returned `token` and `tokenType`, and attaches `Authorization: Bearer <token>` to authenticated calls.

### Secure interactive login

```powershell
python .\gridee.py auth login --email "you@example.com"
python .\gridee.py auth status --live
```

The first command securely prompts for the password. The token not the password is saved under `%LOCALAPPDATA%\gridee-cli\session.json` by default. A saved token is only reused with the API origin that issued it.

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

The reverse-engineered v1.71 references are retained as documentation:

- [Complete API reference](docs/API_REFERENCE.md)
- [Endpoint inventory](docs/API_ENDPOINTS_COMPLETE.md)
- [Authentication/header notes](docs/AUTHENTICATION.md)
- [Earlier endpoint notes](docs/ENDPOINTS.md)

## On-device booking scheduler

The Android helper uses an exact one-shot alarm and an accessibility service to drive the normal Gridee UI. It is dry-run by default and cannot bypass a secure PIN.

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

python .\gridee.py scheduler status
python .\gridee.py scheduler cancel
```

Add `--execute` to the schedule command only when the helper should press final confirmation. Source lives in `android-helper/`; the build output is `android-helper/build/gridee-scheduler-debug.apk`.

## APK analysis notes

The installed-app APK is intentionally not committed to this merged repository. If you are authorized to inspect your local copy, place it at `analysis/gridee-1.71-base.apk` (ignored by Git) and run:

```powershell
$apk = ".\analysis\gridee-1.71-base.apk"
$apkanalyzer = "$env:LOCALAPPDATA\Android\Sdk\cmdline-tools\latest\bin\apkanalyzer.bat"
& $apkanalyzer dex code --class "com.gridee.parking.data.auth.JwtTokenManager" $apk
```

The captured non-secret UI hierarchy used for parser regression testing remains at `analysis/gridee-booking-home.xml`.

## Configuration

ADB defaults can be supplied with `GRIDEE_DEVICE`, `GRIDEE_PACKAGE`, `GRIDEE_ACTIVITY`, `GRIDEE_ADB`, and `GRIDEE_OUTPUT`. API defaults use `GRIDEE_BASE_URL`, `GRIDEE_SESSION_FILE`, `GRIDEE_TOKEN`, `GRIDEE_TOKEN_TYPE`, `GRIDEE_EMAIL`, and `GRIDEE_PASSWORD`.

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
