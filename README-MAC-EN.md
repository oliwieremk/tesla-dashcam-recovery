# Tesla Recovery — macOS instructions (PL / EN)

[Polska instrukcja](README-MAC-PL.md) · [Download](https://github.com/oliwieremk/tesla-dashcam-recovery/releases/tag/macos-v0.3.0)

## Install

1. Download `tesla-recovery-macos-pl-en.zip` from Releases and unzip it.
2. Move **Tesla Recovery.app** into Applications, or keep it in the extracted folder.
3. Double-click the app. Initial setup downloads uv, Python 3.14 and dependencies; internet is required.
4. macOS 13+ is required. The launcher contains Apple Silicon and Intel binaries; only Apple Silicon hardware has been tested.

The app is ad hoc signed, without Apple Developer ID or notarization. If macOS blocks it, use the available Open option in the context menu or Privacy & Security settings. Only override the block for a copy you trust.

## Recover recordings

1. Stop using the Tesla USB in the car, then connect it to your Mac.
2. Select its card, check the name/capacity and choose **Scan selected source**.
3. macOS requests administrator authorization to read the external FAT32/exFAT partition. Enter the password only in the system dialog.
4. Pick a session, drag a time range, or enter exact From/To times. Day filters and zoom help navigate recordings.
5. Select a destination on the Mac and copy the clips. Do not use the source USB as the destination.
6. For encrypted clips, sign in to Tesla or paste an access token, then prepare the recordings. Plain MP4 clips skip authentication.
7. Open the viewer and check recovered clips. Deleted data may already have been overwritten.

The app runs as an ordinary user. A short privileged helper unmounts the selected external partition, opens it read-only and passes access to the app. Internal disks are refused. The USB disappears from Finder while in use; **End USB access** or closing the app remounts it. Do not unplug during an operation. After forced termination, use Disk Utility to mount it again if needed.

If access is denied, review the detailed error and macOS Privacy & Security → Full Disk Access. Terminal may need access for the `.command` script; the `.app` process/runtime may need access when launching through Finder.

## Viewer and languages

The **PL / EN** buttons change and remember the language, including progress, quality descriptions and native menus. Switching preserves the selected range, marked minutes and playback position.

The viewer supports front, back, left/right repeater and left/right pillar clips. Click a camera to enlarge it; **1–6** selects a camera and **0** returns to the grid. **Space** plays/pauses and **Left/Right** seeks five seconds. **⌘ / Ctrl + click** marks minutes; **Shift + click** extends the selection. **Save selection** copies marked minutes to another folder. Telemetry appears only when present in the footage.

Missing clips are indicated. A repaired/shorter clip may contain only part of the original. “Ready to play” means the structure was read successfully, not that all content survived. Check playback to assess completeness.

## Images and libraries

**Open partition image** accepts uncompressed `.img`, `.raw` and `.dd` files starting at a FAT32/exFAT partition boot sector. Whole-disk GPT/MBR and compressed DMG images are unsupported. Images do not require administrator authorization. **Open library** loads a recovered library.

Source and `Tesla Recover.command` are also inside `Tesla Recovery.app/Contents/Resources/app`:

```bash
./"Tesla Recover.command" --image "/path/to/partition.img"
./"Tesla Recover.command" --library "/path/to/recovered-library"
```

## Local files and authentication

Runtime, settings and browser profile: `~/Library/Application Support/TeslaRecover`.
Startup log: `~/Library/Application Support/TeslaRecover/startup.log`.
Recordings are written to the chosen output folder.

For encrypted clips, authentication retrieves clip keys from Tesla. The access token is kept in memory, not settings. The dedicated browser profile can retain sign-in data. Key retrieval needs internet; decryption and playback happen locally. Plain footage needs no token. Actual Tesla login/key retrieval has not yet been verified in this port.

## Verification and limits

18 automated tests passed on Apple Silicon: synthetic exFAT recovery/export, source integrity, read-only access transfer, localization, MP4 repair/decoding and synthetic AES decryption. Native checks covered playback, language switching and the icon. See the [detailed report (PL)](docs/VERIFICATION-PL.md).

Full physical Tesla USB recovery/authorization, a real Tesla account and encrypted recordings, Intel hardware, and real six-camera synchronization/telemetry still require validation. The release contains no recordings or account data.

Original project: [Arquiteto](https://github.com/Arquiteto/tesla-dashcam-recovery). MIT license; unofficial software, not affiliated with Tesla.
