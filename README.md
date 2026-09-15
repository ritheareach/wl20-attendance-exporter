# WL20 Attendance Exporter

Cross-platform desktop app (Windows / macOS / Linux) that downloads all attendance
records from a **ZKTeco WL20 fingerprint terminal** over the office LAN and exports
them to a formatted **Excel (.xlsx)** workbook.

![Attendance tab](docs/screenshot-attendance.png)

- **No server required** — talks straight to the terminal on TCP port 4370 (ZK protocol, read-only).
- **Reused, battle-tested parser** — handles the WL20 firmware quirks (broken record
  counters, 8/16/40-byte records, 22-byte compressed records).
- **Read-only** — never clears, modifies or disables records on the terminal.
- **Exports** attendance records, a daily first-in/last-out summary, device info and a
  diagnostics sheet (bilingual Khmer + English headers).

![Daily summary tab](docs/screenshot-summary.png)

## ការប្រើប្រាស់ (Khmer quick start)

1. ភ្ជាប់កុំព្យូទ័រទៅបណ្តាញការិយាល័យ ដូចគ្នានឹងម៉ាស៊ីនស្កេនស្នាមម្រាមដៃ។
2. បើកកម្មវិធី រួចពិនិត្យ **Address** (លេខ IP របស់ម៉ាស៊ីនស្កេន)។
3. ចុច **Fetch attendance (F5)** ដើម្បីទាញយកទិន្នន័យវត្តមានទាំងអស់។
4. ជ្រើសចន្លោះកាលបរិច្ឆេទ បន្ទាប់មកចុច **Export to Excel… (Ctrl+E)**។
5. ឯកសារ Excel មានសន្លឹក 4៖ វត្តមាន, សេចក្តីសង្ខេបប្រចាំថ្ងៃ, ព័ត៌មានឧបករណ៍, និងរោគវិនិច្ឆ័យ។

## Download

Grab the build for your OS from the **Releases** page (built automatically for
Windows, macOS and Linux by GitHub Actions). The repository is public, so no
GitHub account is needed — download straight from the machine that will run the
app rather than copying it between computers.

| OS | File |
| --- | --- |
| Windows | `WL20-Attendance-Exporter.exe` (single file) |
| Windows (fallback) | `WL20-Attendance-Exporter-windows-folder.zip` — unpack and run the `.exe` inside |
| macOS | `WL20-Attendance-Exporter-macos.zip` (app bundle) |
| Linux | `WL20-Attendance-Exporter` |

No Python installation is needed for the packaged builds. The builds are not
code-signed: on Windows choose *More info → Run anyway* (SmartScreen), on macOS
right-click the app → *Open* (Gatekeeper). Verify the download against
`SHA256SUMS.txt` from the same release.

**Save the file to a real folder before running it.** Launching it straight from
the browser's download bar runs it out of Chrome/Edge's temporary `scoped_dir`,
where the single-file build can fail with *"Could not load PyInstaller's embedded
PKG archive from the executable"* (and antivirus on locked-down machines blocks
exactly that). If the single-file `.exe` still refuses to start, use the
**folder** zip: unpack it anywhere and run `WL20-Attendance-Exporter.exe` inside —
it needs no self-extraction. Verify the hash first:

```powershell
Get-FileHash .\WL20-Attendance-Exporter.exe -Algorithm SHA256
```

The Linux build needs the usual Qt runtime libraries — present on every desktop
install, and available as `libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1`
on a minimal/headless distribution.

## Run from source

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python -m wl20_exporter            # GUI
wl20-export --host 192.168.88.245  # CLI
```

## CLI

```bash
# Everything on the device → Excel
wl20-export --out attendance.xlsx

# A date range, plus a CSV copy of the raw records
wl20-export --from 01-09-2026 --to 15-09-2026 --out september.xlsx --csv september.csv

# Just test the connection / dump diagnostics
wl20-export --test
```

Dates are **DD-MM-YYYY** everywhere — in the app, in the Excel columns, in the CSV
and on the command line (`YYYY-MM-DD` is still accepted).

CLI options: `--host --port --password --timeout --from --to --out --csv --test --verbose`.

## Important: one TCP session per terminal

The WL20 serves **one client at a time**. While this app is reading, the FaceGO
realtime listener on the office server cannot hold its socket, and a fingerprint
scan made during the read may be missed by the live system (the device's own flash
still holds the record — the next FaceGO sync picks it up). Run exports outside
peak hours, or read from the FaceGO API instead when the server is up.

## Build installers

```bash
pip install .[build]
pyinstaller packaging/wl20-exporter.spec
```

`packaging/wl20-exporter.spec` works on all three platforms; `.github/workflows/build.yml`
runs exactly that on every push (tests included) and attaches the Windows, macOS and
Linux builds to a GitHub release on every `v*` tag:

```bash
git tag v1.0.0 && git push --tags
```

Each build is verified after freezing with the packaged app's own smoke test:

```bash
dist/WL20-Attendance-Exporter --selftest   # boots Qt + parser + exporter offscreen
```

## Icon

The app icon is the office **AIFarm** mark (cow head in the yellow frame), derived
from `static/src/AIFarm_Logo _cropped.png` in the FaceGO repo. Regenerate the
`.png` / `.ico` / `.icns` set after any logo change:

```bash
python tools/make_icon.py --source "/path/to/AIFarm_Logo _cropped.png"
```

The window icon loads at runtime from the bundled PNG, so it shows up in the
Windows taskbar, the macOS dock and Linux window lists alike.

## Excel output

| Sheet | Contents |
| --- | --- |
| `Attendance` | Date, Time, Staff ID, Name, Device user ID, Status, Punch, UID |
| `Daily Summary` | Per person per day: first check-in, last check-out, hours, punch count |
| `Device Info` | Device name, serial, firmware, export range, record counts, app version |
| `Diagnostics` | Which parse format decoded the data, raw sizes, warnings |

## Tests

```bash
python -m unittest discover -s tests -v
```

The parser tests use synthetic device payloads, so they run with no device attached.
