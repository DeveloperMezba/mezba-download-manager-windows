# Mezba Download Manger

It is basically an early released version.so It have some bugs. But follow the steps and it will work with your windows version 
perfectly. 

## Installation:
1.download the .exe file and install it.( windows will show a warning and will ask you to don't run it. just click on more info and install it anyways.)

2. It will need internet connection to be installed.

3. after installing it open the app and setup the browser extension to work perfectly.

## Add the browser extension once

### Chrome, Edge, Brave, Chromium, Vivaldi

1. Open MDM → **Browser setup → Open Chromium extension folder**.
2. Open your browser's Extensions page, such as `chrome://extensions` or `edge://extensions`.
3. Turn on **Developer mode**, choose **Load unpacked**, and select:

```text
%LOCALAPPDATA%\Programs\Mezba Download Manager\app\extension\chromium
```
Paste this path into the Windows file picker or browse to the folder opened by MDM. The installer already registers the matching native-messaging host for your account. Do not change the Chromium manifest key.

4. Pin the extension and reload open video pages. Click **↓ MDM** beside a visible video, or use the toolbar button.
5. Choose a video quality/format or audio, then Download. A small progress window opens and the task also appears in the app.

### Firefox

Open `about:debugging` → This Firefox → Load Temporary Add-on. Choose:

```text
%LOCALAPPDATA%\Programs\Mezba Download Manager\app\extension\firefox\manifest.json
```

This is an unsigned preview, so Firefox removes the temporary add-on after restarting. Permanent normal Firefox distribution requires Mozilla signing. The installer cannot silently add extensions to your browser.

### Mezba Download Manager for Windows 0.1.2

Windows edition of MDM, based on Linux 0.3.1. Includes MP4/MKV video, audio, playlist downloads, a browser companion, compact progress windows, resumable direct files, a download queue, public Google Drive files, and manual GitHub update checks.

#### Windows 0.1.2: completion fix and separate tool updates

This release intentionally corrects the version sequence to **0.1.2**, replacing the earlier build labelled 1.1.0. It fixes a Windows MP4 finalization error: the converter opened its finished temporary file read-only before calling `os.fsync`, which Windows can reject with `[Errno 9] Bad file descriptor`. The final flush now uses a writable handle before publishing the output. Real conversion and disk failures still remain errors, and the source file is preserved.

The familiar layout remains, with subtle card borders, a selected sidebar state, slimmer progress bars and clearer status colors. The new **Update** button opens two options: **App update** and **Download tools**.

1. Pause downloads, close MDM and its progress windows, and exit Chrome/Brave.
2. Run `Mezba-Download-Manager-0.1.2-Windows-x64-Setup.exe` under the same Windows account. Install over your current copy; keep your downloads and State folder.
3. Reopen MDM. In your browser's Extensions page, reload MDM and confirm version **0.1.2**, then refresh video pages. If your browser will not reload the lower version number, remove only the extension and Load unpacked again from the installed folder below.
4. For an old task still marked Error, click **Retry** using its existing folder and format. The engine reuses retained downloads where possible and performs finalization again. Existing error records are not silently reclassified as complete.

The screenshot error and a matching code defect were identified. The supplied installer is built on Linux; actual Windows Chrome/Brave end-to-end verification still needs your PC. See `docs/TEST-REPORT.md` for the precise checks performed.






## Download options

The scrollable menu includes the current video/audio and, when detected, full-playlist video/audio. Keep playlist information in the link, such as a YouTube `list=` parameter. A playlist task produces separate numbered files. Completed items are recorded so retries can skip them.

- **MP4:** H.264 video with 8-bit YUV420p and AAC audio when audio exists. Compatible streams copy directly; other streams convert using FFmpeg. Conversion may take time and additional space. For older devices, start with 720p or 1080p.
- **MKV:** preserves the source video/audio codecs without re-encoding.
- **Audio:** original quality or MP3 conversion.
- **Direct files:** paste the file URL or right-click a browser link → Download with MDM.
- **Google Drive:** use a public single-file sharing link. Private Drive OAuth, folders, quota bypass, and Google Docs exports are not supported.

The native Windows interface keeps the dark mint/slate style and controls, using Tk instead of Linux GTK. Native fonts, spacing, and window borders differ. The browser interface is carried over from the Linux version.

## Large files, pausing and recovery

The direct HTTP engine streams in bounded buffers and uses 64-bit file offsets. Segmented resume requires server byte-range support and a stable ETag/Last-Modified validator. MDM refuses to append to a changed or unverifiable file. Use Details → Replace expired link after pausing a direct-file task.

Closing the app/progress window leaves downloads running. Preferences → Stop background service stops MDM. After a crash or reboot, reopen MDM and resume recovered paused jobs. There is no login startup service or protection against sleep in this release.

Use **NTFS or exFAT** for large files, not FAT32. Keep partial files and `.mdm-state` checkpoints. Leave extra space for merging/conversion. MP4 conversion restarts from the preserved downloaded source after an interruption. Video/Drive resume is handled by their engines and depends on the source.

Windows Job Objects are used to stop media subprocesses when the owning service exits. This Windows-specific behavior still needs a real Windows test. The Python service uses authenticated, per-user loopback IPC. It is not an HTTP server and is not exposed on the network. Its random access token is in the current user's state folder; setup restricts that folder's Windows permissions to the user.

## Updates

Click **Update** in the sidebar. A small in-app window offers:

### App update

Open App update, enter your trusted GitHub `owner/repository` (or repository URL), then click **Check & install update**. MDM remembers the repository. Your public release must contain the Windows Setup EXE and `SHA256SUMS`. The installer is verified before it runs. Setup preserves your download history and settings.

No repository was supplied with this request, so the field is ready for you to fill in. The GitHub build workflow automatically embeds the repository it runs in. Use a separate Windows repository from Linux. Because the numbering changed, publish **v0.1.2** and explicitly mark it as **Latest**. Legacy tags `v1.0.0` and `v1.1.0` are rejected by this release's updater to avoid installing the old build again. The next release should be **v0.1.3**. See `docs/BUILD-AND-PUBLISH.md`.

### Download tools

Click **Check & update tools** to update tools independently of MDM:

- **yt-dlp** and its **EJS** JavaScript helper.
- **Deno**.
- **FFmpeg and ffprobe** together.
- **gdown** for Google Drive and the compatible Python dependencies used by these packages.

Installed versions appear in the window. Python packages come from PyPI as resolved, SHA-256-pinned wheels; Deno and FFmpeg come from their configured upstream GitHub releases with SHA-256 verification. A replacement bundle is installed and smoke-tested separately. Downloads continue during preparation, then briefly pause for the switch and resume if they were running. Previously paused tasks stay paused. The previous bundle is retained. Download or validation failures do not switch the active tools. Closing the update window or main app leaves the service performing the update.

A new upstream version does not immediately break the old one. Website changes can make older download tools stop working, which is why independent updates are useful. These checks cannot guarantee support for every website or future tool release. Python/Tk itself remains part of MDM's app installer. A tool requiring a newer Python runtime may require a later MDM app release.

Allow about **1 GB free space** for staging a tool update, with additional space for retained tool bundles. Downloads use the verified newer bundle on their next start. There is no automatic background update polling, no system-wide pip installation, and no system PATH change. Reload the browser extension after an **app** update; a tools-only update does not require an extension reload.

To update the app manually, pause downloads, close MDM and your browser, and run the new Windows installer. Do not install a Linux ZIP over this Windows edition.

## Troubleshooting

- **Setup cannot download tools:** verify internet access and that GitHub release downloads are reachable, then rerun the installer. Read the installer details. It verifies hashes and does not install a corrupt download.
- **Browser cannot connect:** use the installed extension folder above, reload it, and reopen the video page. Do not load the extension from an extracted source archive. Run the installer under the same Windows account as the browser.
- **A video is not found:** open its individual video/reel/post page. Try the toolbar and detected sources. Site login rules, unsupported formats, anti-bot blocks, deleted sources, and DRM can prevent downloading.
- **Chrome/Brave cookie error:** for public videos, set Preferences → Signed-in browser session to **Off** and retry. For media that requires login, a supported Firefox session may work. Do not disable browser cookie encryption or Windows protections.
- **Signed-in videos:** optionally select your browser in Preferences. Cookie/keyring restrictions, especially newer Chromium cookie protections, can still prevent access. No cookies are sent to an MDM cloud service.
- **MP4 takes time at 100%:** FFmpeg may still be merging or converting. Check the processing message. Do not delete its intermediate files.
- **Windows paths are too long:** use a shorter download folder, such as `D:\MDM`.
- **An interrupted update blocks startup:** close MDM, run the same/newer installer again, and let it finish. The installer repairs its update marker and restores the queue when possible.

Diagnostic command in PowerShell, after installation:

```powershell
& "$env:LOCALAPPDATA\Programs\Mezba Download Manager\runtime\python.exe" "$env:LOCALAPPDATA\Programs\Mezba Download Manager\app\mdm.py" --doctor
```

Logs/history/settings are under:

```text
%LOCALAPPDATA%\Mezba Download Manager\State
```

Do not publish queue databases, logs, cookies, or temporary URLs that may contain access tokens.

## Uninstall

Close MDM and its browser progress windows. Use Windows Settings → Apps → Mezba Download Manager → Uninstall, or run its `Uninstall.exe`. Downloaded files and history/settings are preserved. Remove the browser extension separately. To remove saved history too, stop MDM first and delete its State folder yourself.

## Verification status

The installer and launchers are real Windows PE executables compiled from the included source. The build environment is Linux. Windows installation, Tk rendering, Registry integration, Job Objects, and playback have **not been executed on a Windows machine** here. See `docs/TEST-REPORT.md` for tests that were actually run and the remaining Windows checks. This is an initial Windows preview, not a claim of a fully tested production release or complete IDM parity.
