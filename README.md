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

| OS | File | What it is |
| --- | --- | --- |
| Windows | `WL20-Attendance-Exporter-Setup-<version>.exe` | normal installer: per-user (no admin rights needed), Start Menu entry, uninstaller |
| Windows (portable) | `WL20-Attendance-Exporter.exe` · `-windows-folder.zip` | run without installing (the zip is for machines where antivirus blocks the single file) |
| macOS | `WL20-Attendance-Exporter-macos.dmg` | open the disk image and drag the app to Applications |
| macOS (zip) | `-macos.zip` | the same app bundle without the disk image |
| Linux | `WL20-Attendance-Exporter` | single-file executable (chmod +x and run) |

**Nothing to install first.** These builds carry their own Python and Qt inside, so
they run on a computer that has never had Python on it and where you cannot install
anything — no Python, no pip, no dependencies, no admin rights. CI checks this on
every build: the bundled interpreter must be inside the app, and the frozen app is
started with an emptied environment (no Python reachable at all) before it ships.

The builds are not code-signed, which is a separate matter: on Windows choose
*More info → Run anyway* (SmartScreen) the first time, on macOS right-click the app →
*Open* (Gatekeeper). Verify the download against the `SHA256SUMS` file from the same
release.

Each release is built and then **installed/mounted on its own platform by CI**: the
Windows installer is run silently from PowerShell and the installed app is executed,
and the macOS disk image is mounted and the app inside it is launched — so a broken
installer cannot reach the Releases page.

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

CLI options: `--host --port --password --timeout --from --to --out --csv --test --verbose`
plus the retry flags below.

## If the terminal is busy, offline or rebooting

The WL20 handles one read at a time and is unreachable while it reboots, so an export
has to wait it out instead of failing:

- **In the app**: *Retry if the terminal is busy or offline* is on by default. It keeps
  trying for up to 5 minutes, logging every attempt, and the **Stop** button cancels the
  wait immediately.
- **CLI**: `--retries N` (attempts, default 1) with `--retry-delay SECONDS`, or
  `--wait-for-device SECONDS` to keep trying until that deadline regardless of attempts.
- **Terminal genuinely wedged?** Reboot it remotely — see below.

## Restarting the terminal

The app can reboot the terminal over the ZK protocol (`CMD_RESTART`). Attendance records
live in the terminal's flash, so a reboot never loses them; the terminal is offline for
roughly 1-2 minutes, and anything else reading it reconnects by itself when it returns.

- **In the app**: the **Restart terminal** button (it asks first), and the optional
  *Restart the terminal if reads keep failing* — off by default, a last resort that
  reboots and reads once more when the retries above are used up.
- **CLI**: `wl20-export --restart` reboots and waits for it to come back (exit 0 when it
  does); `--restart-if-needed` lets a normal export reboot the terminal if it stays
  unreadable, and `--restart-wait SECONDS` (default 180) sets how long to wait after a
  reboot.

A terminal that is completely unreachable cannot be rebooted remotely — there is nothing
to send the command to — so the app only waits in that case.

## When the terminal cuts its log short

This WL20 firmware announces its whole log but transfers only its **first 4096 bytes**,
and it refuses every way of asking for the rest (chunk command, stream ACK, other
ports — all tested against the terminal). The window starts at the *oldest* record, so
once the log passes roughly 186 records the newest punches stop appearing and no fetch
can ever include them. Reads in that state are marked in the export's Diagnostics sheet.

The way out is to start the log over, and the app does it in one action:

- **In the app**: **Reset terminal log …** — it writes a safety export of everything the
  terminal currently hands over, then erases the terminal's attendance log. Users,
  fingerprints and settings are untouched. Every punch from then on is readable again.
- **CLI**: `wl20-export --clear-after-export` does the same, and it can only ever run
  after a workbook is written (no export, no erase).

Unattended daily export on the Jetson (waits up to 10 minutes for the terminal):

```bash
mkdir -p ~/wl20-exports
crontab -e     # then add, on one line:
# 30 18 * * * cd ~/Desktop/wl20-attendance-exporter && .venv/bin/wl20-export --from $(date +\%d-\%m-\%Y) --to $(date +\%d-\%m-\%Y) --wait-for-device 600 --out $HOME/wl20-exports/$(date +\%d-\%m-\%Y).xlsx >> $HOME/wl20-exports/cron.log 2>&1
```

On Windows the same command works under Task Scheduler.

## Important: the app talks only to the terminal

There is no server, database or service in this picture: the app opens its own socket to
the terminal's address, reads its flash memory and closes it again. Nothing else has to
be running, and the app does not read from — or write to — any other system.

The consequence is that the terminal serves **one client at a time**: while another
program or another export window is reading it, a read here can be slow or time out, and
a fingerprint scan made during a read may reach that other program a moment late (the
terminal's flash keeps the record either way). Run exports outside peak hours if reads
time out.

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

The app icon is the office **AIFarm** mark (cow head in the yellow frame), generated
from the office logo file by `tools/make_icon.py`. Regenerate the `.png` / `.ico` /
`.icns` set after any logo change:

```bash
python tools/make_icon.py --source "/path/to/AIFarm_Logo _cropped.png"
```

The window icon loads at runtime from the bundled PNG, so it shows up in the
Windows taskbar, the macOS dock and Linux window lists alike.

## Excel output

The workbook mirrors the office attendance log: one sheet per day, named DD-MM-YYYY,
newest day first, with the usual seven columns:

| No. | Staff ID | Staff Name | First Check-in | Last Check-out | Total Hours | Status |
| --- | --- | --- | --- | --- | --- | --- |

- Times are **HH:MM**, hours read like the log (`9h31mn`), and a day with no check-out
  yet leaves the last check-out and the hours blank and reads **Present** (otherwise
  **Completed**).
- Header style is the office palette (white on `#366092`); nothing else is decorated.
- `--punches` adds a raw punch-list sheet per day (each punch on its own row, for
  auditing) and `--details` adds the Device Info and Diagnostics sheets used for
  troubleshooting. Both are off by default; the Diagnostics sheet also appears on its
  own whenever a read was incomplete, so a partial export never looks complete.

## Tests

```bash
python -m unittest discover -s tests -v
```

The parser tests use synthetic device payloads, so they run with no device attached.
