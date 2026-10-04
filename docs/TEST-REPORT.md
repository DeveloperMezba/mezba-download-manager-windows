# Windows 0.1.2 verification

Date: 2026-09-28.

## Diagnosis and correction

The supplied screenshot reports `Download engine failed (exit code 1). ERROR: [Errno 9] Bad file descriptor` at 100%. A matching defect exists in MP4 finalization: `CompatibleMP4PP.run` flushes a read-only temporary output file. Windows flushing requires a writable handle. Version 0.1.2 opens it as `r+b`, flushes it, then atomically publishes it. Failed conversion or disk flush still raises an error and retains the source. The actual Chrome/Brave incident has not been reproduced on Windows here.

Reference: Microsoft FlushFileBuffers documentation, https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers .

## Checks performed for 0.1.2

- Python regression suite: 61 tests ran, 58 passed and three Windows-only tests were skipped. A subsequent targeted six-test app/platform run passed, including one newly added legacy-number regression (59 distinct passing Python tests in total). Coverage includes existing local HTTP downloads, resume/recovery, actual yt-dlp/FFmpeg downloads and MP4 conversion, playlists, IPC and worker supervision. Added Windows-style writable-flush regression and real disk-error preservation tests.
- Ten tool-update regressions cover exact checksum/size, URL and release validation, archive handling, bundle selection, retention, failed staging, failed activation and restoring only the previously active queue.
- App-update checks cover the corrected 0.1.3 next-release path, checksum/repository enforcement and rejection of legacy 1.1.0.
- Three Windows Job Object integration cases remain skipped on Linux. They remain included in the Windows CI workflow.
- Browser tests: nine background checks, popup/menu routing and keyboard/viewport checks, and progress/completion/reconnection checks passed using Node/jsdom.
- Staged updater exercised with real PyPI resolution, SHA-256-pinned wheel installation into a temporary bundle, imports of yt-dlp/EJS/gdown, the MDM MP4 postprocessor API, local FFmpeg H.264/AAC smoke conversion and bundle activation. Windows tool ZIPs were fixtures and FFmpeg execution used Linux FFmpeg in this particular test; this does not claim native Windows updater execution.
- Upstream GitHub metadata for the configured Deno and FFmpeg releases was queried. Both supplied the expected Windows ZIP and SHA-256 digest.
- Main UI and Update window rendered with Tk on a Linux virtual display and were visually inspected. Windows fonts, borders and DPI can differ.
- Python source compilation completed. Both browser extension identities are preserved and their versions are 0.1.2.

## Build

Both 64-bit Windows launchers are rebuilt from the included C/resource source. The 32-bit NSIS setup stub installs the 64-bit app. The unchanged private Windows runtime is reused byte-for-byte from the supplied 1.1.0 installer; the original lock files and normal build workflow are retained. The installer includes the corrected app source and new tool updater, with SHA256SUMS generated for this build. Its initial FFmpeg/Deno downloads are still verified during installation.

## Remaining Windows verification

A real Windows computer was unavailable. A Wine attempt could not start its server in this environment. No Windows browser, Registry integration, installer upgrade or native Job Object execution is claimed. Confirm on Windows 10/11: install over the old release, reload the extension as 0.1.2, retry the affected MP4, and verify both the app and popup show Completed and the MP4 plays. Also exercise a tool update on Windows before distributing broadly.

The original historical build report is retained separately as TEST-REPORT-1.1.0.md. This unsigned release is a tested code fix and compiled installer, not a claim of full Windows end-to-end validation.
