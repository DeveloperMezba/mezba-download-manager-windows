# Changes

## Windows 0.1.3

- New look: refreshed desktop app and browser extension (popup, progress window, in-page button) with status colours, count badges, rounded progress bars and clearer buttons.
- Smoother list: downloads update in place, so no more flicker, lost scroll position or restarting progress animation every second.
- Dialogs now size to their content and follow Windows display scaling (fixes clipped buttons at 125%/150%); they open centred, close with Esc, never stack, and support Enter. Dropdown lists match the dark theme.
- DPI-aware, crisp text; window size/position is remembered; app icon shown in the window.
- Ctrl+N (new download), Ctrl+F (search), auto-detects video links, pre-fills a copied link, friendlier ETA (2h 07m instead of 7620s).
- "Open MDM" from the browser now brings the already-open window to the front instead of doing nothing.
- Stop background service asks for confirmation.
- Extension: removed wrong "Linux" wording; Enter key in the popup; detected video sources no longer vanish when the browser puts the extension to sleep; scrolling pages with players is lighter.
- Service: a damaged settings/history file no longer prevents startup; the scheduler survives a failed task; clearer validation messages; a download engine that stays silent for 4 minutes is stopped with an actionable error instead of hanging.
- Tests added for these changes. Windows installer must be built by the GitHub workflow (tag v0.1.3).

## Windows 0.1.2

- Correct the release number to 0.1.2, intentionally replacing the earlier 1.1.0 label.
- Fix MP4 finalization on Windows: flush the converted file through a read/write handle to avoid Errno 9 after transfer/conversion.
- Keep genuine conversion, disk-flush and playlist failures visible; retry uses retained source data.
- Add Update with separate App update (saved GitHub repository) and Download tools options.
- Stage, verify and test independent yt-dlp/EJS, Deno, FFmpeg/ffprobe and gdown/dependency updates. Commit one bundle pointer after active downloads stop; then restore the previous active queue.
- Keep the previous tool bundle and preserve current tools on failed staging/validation.
- Small UI polish: selected sidebar state, card outlines, status colors and progress bars; preserve Completed in the desktop progress window after a later connection failure.
- Add MP4 flush and tool-updater regression coverage. Keep Windows CI integration checks.

## Earlier build history

## Windows 1.1.0

- Keep the Windows supervisor outside its kill-on-close job. Assign only the suspended engine, resume after assignment, and preserve the actual exit code. Close handles and terminate descendants on failure/service exit.
- Launch the background service independently of browser jobs where Windows permits breakaway; retry normal launch when that permission is unavailable. No changes to browser or OS security policies.
- Preserve confirmed Completed state when a browser popup loses its connection. Final single-file byte counts are taken from the saved output.
- Replace Linux-only repair instructions with Windows instructions. Keep engine exit codes in errors and add specific Chrome/Brave cookie guidance.
- Add worker success/failure, service-death, startup-fallback and completion regression tests. Real Win32 integration tests are included for Windows CI.
- No layout, styling, extension identity, download format, runtime package or user-data migration changes.
- Native Chrome/Brave reproduction remains unverified; the original exact error was not provided.

## Windows 0.1.0

- Initial Windows edition, based on Linux MDM 0.3.1.
- MP4/MKV video, original audio/MP3, full playlists, scrollable browser choices.
- Native Windows desktop queue and small progress windows.
- Windows-safe file offsets, filenames, completion rename, locks, and process supervision.
- Authenticated loopback service, per-user native-host registration, private runtime.
- Compiled one-click NSIS installer, Start menu/Desktop shortcuts, uninstaller.
- Manual GitHub Windows release updates with checksum verification and installer recovery.
- Full MDM source and reproducible build inputs included.
