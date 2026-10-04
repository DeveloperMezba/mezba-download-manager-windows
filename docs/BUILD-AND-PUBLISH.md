# Build and publish MDM Windows

The supplied setup EXE is already compiled. These instructions are for changing the source and publishing your own releases. This Windows bugfix release is **0.1.2**, replacing the legacy-numbered 1.1.0 build with a Windows completion fix, subtle UI polish and separate download-tool updates. Keep Windows and Linux in separate repositories so their release/version sequences do not conflict.

## Source layout

`source/mdm.py` is the Python entry point. `source/mdm/` contains the queue, HTTP/media engines, Windows UI, native host, updater, and OS support. `source/setup_windows.py` installs media tools and native-host registry entries. `source/extension/` contains both browser builds. `build/launcher.c` creates native Windows launcher EXEs; `build/installer.nsi` creates the setup EXE. `build/build.py` assembles the private runtime, verifies pinned downloads, compiles launchers, and compiles the installer.

The Python and Tcl/Tk runtime downloads are pinned in `build/python-runtime-lock.json`. Python wheel URLs and SHA-256 values are in `build/python-packages-lock.json`. FFmpeg and Deno downloads performed on the user's computer are pinned in `source/media-tools-lock.json`.

## Build on Windows

Requirements for **developers only**:

- 64-bit Windows 10/11.
- Python 3.10 or newer for running the build script.
- MinGW-w64 GCC and windres, available through MSYS2 or another trusted MinGW-w64 distribution.
- NSIS 3 with its usual include files/plugins.
- Internet access for pinned dependency downloads.

These developer tools are not needed by people installing the finished EXE.

In PowerShell, from the project root, download the pinned Python assets and extract the Tcl/Tk MSI with Windows Installer:

```powershell
New-Item -ItemType Directory -Force build-cache | Out-Null
$items = Get-Content build/python-runtime-lock.json | ConvertFrom-Json
foreach ($item in $items) {
    $path = Join-Path (Resolve-Path build-cache) $item.name
    Invoke-WebRequest $item.url -OutFile $path
    if ((Get-FileHash $path -Algorithm SHA256).Hash.ToLower() -ne $item.sha256) {
        throw "Checksum mismatch: $path"
    }
}
$tcl = Join-Path (Resolve-Path build-cache) 'tcltk'
New-Item -ItemType Directory -Force $tcl | Out-Null
$msi = Join-Path (Resolve-Path build-cache) 'tcltk.msi'
$p = Start-Process msiexec.exe -ArgumentList "/a `"$msi`" /qn TARGETDIR=`"$tcl`"" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Tcl/Tk administrative extraction failed' }
python build/build.py --cc gcc --windres windres --makensis "${env:ProgramFiles(x86)}\NSIS\makensis.exe" --tcltk-extracted $tcl
```

Put your MinGW-w64 `bin` folder on the current terminal's PATH first, or pass absolute compiler paths. `--tcltk-extracted` must point to the directory containing `Lib/tkinter`, `DLLs/_tkinter.pyd`, and `tcl`. The script downloads and verifies all remaining wheel files automatically.

Output:

```text
dist/Mezba-Download-Manager-0.1.2-Windows-x64-Setup.exe
dist/SHA256SUMS
```

The private runtime is about 57 MiB before installer compression. The media tools are downloaded separately during setup so they do not inflate the installer. Do not substitute unverified executable downloads.

## Cross-build on Linux

Install Python 3, MinGW-w64, NSIS and msitools using your distribution's package manager. Then run:

```bash
python3 build/build.py
```

Compiler/tool paths can be set with `--cc`, `--windres`, `--makensis`, and `--msiextract`. This produces Windows PE executables; it does not make them executable on Linux or prove Windows runtime behavior. Run the Windows checks in TEST-REPORT.md before declaring a production release.

## Test changes

Install development-only test dependencies in a separate Python environment:

```text
python -m pip install "yt-dlp[default]" gdown
python -m unittest discover -s source/tests -p "test_*.py" -v
node source/tests/test_extension.cjs
```

Media tests require FFmpeg/ffprobe on PATH. DOM tests additionally require Node.js and jsdom outside the app:

```text
npm install --prefix test-deps jsdom
```

Set NODE_PATH to the absolute `test-deps/node_modules` directory, then run `node source/tests/test_menu.cjs` and `node source/tests/test_progress.cjs`. jsdom is not an application runtime dependency.

## Upload all source to GitHub

Create an empty **public** repository at https://github.com/new, for example `mezba-download-manager-windows`. Do not pre-create a README. From this project root, use your GitHub account through GitHub CLI or Git Credential Manager:

```text
git init
git branch -M main
git add .
git commit -m "Add MDM Windows 0.1.2"
git remote add origin https://github.com/YOUR-USERNAME/mezba-download-manager-windows.git
git push -u origin main
```

The included `.gitignore` excludes generated payloads, downloaded build caches, personal runtime state, and the packaged installer directory. Upload source, not installed application folders. Never commit personal cookies, queue databases, logs, or private URLs.

## Publish the actual installer

The included GitHub workflow builds/tests on Windows when a `vX.Y.Z` tag is pushed. It embeds the repository name into `source/update-source.json` before building. It needs GitHub Actions enabled and the workflow's `contents: write` permission.

For your first release:

```text
git tag v0.1.2
git push origin v0.1.2
```

Check the Actions log. The workflow is supplied for your use; it has not been executed on your repository by this build. If it fails, fix the issue before publishing.

For a manual release, set `source/update-source.json` to your repository, rebuild, and use GitHub → Releases → Draft a new release. Choose `v0.1.2`, upload the actual setup EXE and `SHA256SUMS`, leave prerelease unchecked, and mark the release as Latest. Disable the automatic publishing workflow before pushing the tag if you plan to publish manually.

The app requires these exact asset names, using the matching version:

```text
Mezba-Download-Manager-0.1.2-Windows-x64-Setup.exe
SHA256SUMS
```

GitHub's autogenerated source ZIP is not the installer. A source-only release will not update an installed app. Share the repository's `/releases/latest` page with users.

## Future versions

Run `python build/bump_version.py 0.1.3`, update CHANGELOG.md, test, and rebuild. Commit/push your changes, create tag `v0.1.3`, and push it. Use higher versions each time; do not overwrite published installers or reuse release tags.

Installed users configure the Windows repository once in Check for updates. They then click the same button to download and run a verified newer installer. There are no scheduled background checks. They must reload the browser extension after app updates.

This initial updater keeps the private Python runtime and native launcher stable. A future release that changes the Python ABI, native launcher, runtime packages, or install layout needs a dedicated migration/full reinstall path; do not silently publish such changes as an ordinary app-only update. Preserve the existing Chromium key and Firefox ID.

The unsigned installer can be code-signed by you with your own Windows code-signing certificate. Sign before calculating SHA256SUMS and before publishing. No publisher identity, signing certificate, GitHub account, repository, or release was created for you.

Official references:

- Python application-local distribution: https://docs.python.org/3.13/using/windows.html#the-embeddable-package
- NSIS: https://nsis.sourceforge.io/Docs/
- Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- GitHub releases: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository

## Corrected numbering and independent tools

This release deliberately resets the Windows series to 0.1.2. Mark v0.1.2 as the latest GitHub release, even if legacy 1.x tags exist. The workflow uses `--latest`. Continue with 0.1.3. The updater rejects the legacy 1.0.0 and 1.1.0 tags.

`source/sitecustomize.py` and `source/mdm_components.py` must remain in the installed app folder. The private runtime's existing `_pth` includes `../app` and `import site`, which loads the selected verified tool bundle for every engine subprocess. Updated tools live under the install directory's `components` folder. App upgrades preserve that folder; uninstall removes it.

The supplied 0.1.2 installer reuses the unchanged private runtime extracted from the user's 1.1.0 installer, and recompiles both launchers and the NSIS setup from the included source. The normal build script can reconstruct the runtime from the unchanged lock files.
