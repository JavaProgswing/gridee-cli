# Gridee CLI

A standard-library-only ADB / UIAutomator tool that drives the Gridee Android
app over USB. Its main job is the **reward flow**: tap _Earn -> Watch & Claim_,
let each rewarded ad play, and verify the Wallet credit — repeating until a
target balance (or top-up amount) is reached.

## Objectives

- Automate the rewarded-ad Wallet top-up on your own device, hands-free.
- Detect ad state via the **activity focus** and confirm rewards via the app's
  **"Wallet Updated" notification** — reliable even when uiautomator wedges.
- **Pipeline** ads: start the next ad without waiting for the previous reward to
  credit, so throughput is limited by ad length, not credit lag.
- **Tap safety**: gate every tap on Gridee being foreground; if an ad opens the
  Play Store, back out and retry.

## Requirements

- Python 3.10+ (no third-party packages)
- Android platform-tools (`adb`) on your `PATH`
- A device with **USB debugging** enabled and authorized

## Installing ADB

`adb` ships in Google's **platform-tools**. Any one of these works:

1. **Standalone platform-tools:**
   [download](https://developer.android.com/tools/releases/platform-tools),
   unzip, and add the folder to `PATH`.
2. **Android Studio:** platform-tools installs under the SDK, e.g.
   `%LOCALAPPDATA%\Android\Sdk\platform-tools` (Windows) or
   `~/Library/Android/sdk/platform-tools` (macOS). Add that to `PATH`.
3. **Package manager:**
   - Windows: `winget install Google.PlatformTools` (or `choco install adb`)
   - macOS: `brew install android-platform-tools`
   - Debian/Ubuntu: `sudo apt install android-tools-adb`

If `adb` is not on `PATH`, point the CLI at it with `--adb /path/to/adb` or
`GRIDEE_ADB=/path/to/adb`.

## Enabling USB debugging (on the phone)

1. Settings -> About phone -> tap **Build number** 7× to unlock Developer options.
2. Settings -> Developer options -> enable **USB debugging**.
3. Plug in USB, then **Allow** the debugging prompt on the phone.
4. Confirm: `adb devices` should list the device as `device`.

## Usage

```bash
python gridee.py devices             # list connected devices
python gridee.py balance             # print Wallet balance
python gridee.py reward --earn 200   # earn 200 more coins, then stop
python gridee.py reward --target 2000  # run ads until the balance hits 2000
python gridee.py --device SERIAL reward
```

Run `python gridee.py --help` (or `python gridee.py reward --help`) for the full
list of commands and options. `GRIDEE_DEVICE`, `GRIDEE_PACKAGE`, `GRIDEE_ADB`,
and `GRIDEE_OUTPUT` set the defaults.

## License

MIT — see [LICENSE](LICENSE).
