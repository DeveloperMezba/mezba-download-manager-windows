# Windows 1.1.0 build verification

Build date: 2026-09-27.

## What was actually built

- A native 64-bit Windows GUI launcher and native-messaging launcher, compiled with MinGW-w64 GCC.
- A real NSIS self-extracting Windows installer. Its installer stub is 32-bit and runs on 64-bit Windows; the installed Python/runtime/application launchers are 64-bit. Setup rejects unsupported Windows versions/architectures.
- A private CPython 3.13.15 Windows runtime with matching Tcl/Tk, SQLite, SSL, VC runtime DLLs, and 18 pinned Windows-compatible Python wheels.
- FFmpeg and Deno installer download URLs, sizes and SHA-256 hashes are pinned from their upstream release metadata. These large tools are downloaded on the user's computer, not embedded in the installer.

The installer was successfully compiled on Linux. PE headers, imported runtime DLL names, native extension architecture, payload completeness, hashes, and NSIS compilation were checked. The bundled runtime contains the referenced non-system DLLs. This is not a Linux script renamed to EXE.

## Automated tests

- 47 Python tests passed, including actual local HTTP/media transfers, native-message framing, TCP daemon crash/restart recovery, MP4 conversion and playlists. Three actual-Windows integration tests were skipped on Linux.
- Direct download tests use deterministic 8 MiB data with SHA-256 checks. They cover segmented writes, interruption, pause/resume, changed source validators, replacement URLs, missing range/validator support, wrong ranges, zero-length files, no overwrite, and recovery after a force-killed worker/service.
- A sparse-file fixture checks offsets beyond 100 GiB. It is not a real 100 GB download.
- Actual yt-dlp/FFmpeg tests generate local video/audio. They check MKV, H.264/AAC MP4, original/MP3 audio paths, full playlists, ordered names, archive skipping and retries, and failed conversion preservation.
- Windows seek/write fallback is exercised with simultaneous segment writers on Linux. Reserved Windows filenames, authenticated IPC rejecting wrong tokens, GitHub repository/version validation, and verified installer download are checked.
- 9 extension background checks pass. jsdom tests cover 80-choice scrolling constraints, keyboard selection, 12 viewport positions, MP4/playlist routing, progress, pause/resume/retry, and reconnection.
- All Python source compiles. The Chromium/Firefox versions and preserved extension identities are checked.

## Bugfix regression checks

- The supervisor state-machine tests cover zero/nonzero engine exits, containment before execution, failed assignment cleanup, owner death and closing every owned handle.
- Launch tests cover permitted job breakaway, normal-launch fallback only on Windows access-denied, and propagation of unrelated errors.
- The browser DOM test checks that a confirmed completed download stays Completed after a native-host disconnect.
- Three Windows-only tests exercise actual Win32 successful output (including Unicode), exit-code propagation, and engine/grandchild termination after service death. They are included in the Windows workflow, but were not executed here.
- Microsoft documents that kill-on-close terminates all associated job processes; the previous supervisor placed itself inside that job. The revised supervisor holds the job outside it and assigns the engine suspended before execution. This removes that unsafe reporting/cleanup coupling. This is a code diagnosis, not proof of the user's exact browser failure.
- An inherited browser job and inaccessible Chromium cookies are possible separate startup failures. Permitted breakaway and clearer error guidance address those paths; no browser policy or cookie protection is disabled.

References: https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject and https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects ; upstream cookie limitations: https://github.com/yt-dlp/yt-dlp/issues/7271 and https://github.com/yt-dlp/yt-dlp/issues/10927 .

## What is not yet verified

No Windows VM or physical Windows computer was available here. The following still require real Windows testing:

1. First installation and the complete media-tool download/extraction sequence.
2. Tk rendering, fonts, DPI/scaling, keyboard/mouse behavior, and popup placement.
3. Native Windows launcher standard-handle forwarding to a real browser, per-user Registry registration, and Edge/Chrome/Firefox integration.
4. Windows file locks, NTFS/exFAT file operations, Windows ACL setup, and Job Object termination of media process trees.
5. Full GitHub installer update, rollback, restart, uninstall, and locked-file behavior.
6. Actual playback on the user's devices, live/authenticated websites, and a 60/100 GB network transfer.

The Linux tests do not prove these Windows-specific behaviors. The included Windows GitHub workflow is intended to run source tests, build the installer, and smoke-test the private runtime/Tk on a Windows runner. That workflow has not run on the user's repository here.

This is an unsigned Windows bugfix build. Publishing a broadly tested production release requires the checks above and, if desired, the publisher's own code-signing certificate.
