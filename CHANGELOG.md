# Changes

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
