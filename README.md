# Mezba Download Manager for Windows

<p align="center">
  <strong>A modern, lightweight download manager for Windows with browser integration, media downloading, queue management, resume support, and background downloads.</strong>
</p>

<p align="center">
  <a href="https://github.com/DeveloperMezba/mezba-download-manager-windows/releases/latest">
    <img src="https://img.shields.io/github/v/release/DeveloperMezba/mezba-download-manager-windows?label=Latest%20Release" alt="Latest Release">
  </a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-blue" alt="Windows 10 and 11">
  <img src="https://img.shields.io/badge/Architecture-x64-informational" alt="64-bit">
  <img src="https://img.shields.io/badge/Status-Active%20Development-orange" alt="Active Development">
</p>

<p align="center">
  <a href="https://github.com/DeveloperMezba/mezba-download-manager-windows/releases/latest"><strong>Download Latest Version</strong></a>
  •
  <a href="https://github.com/DeveloperMezba/mezba-download-manager-windows/issues">Report a Bug</a>
  •
  <a href="https://github.com/DeveloperMezba/mezba-download-manager-linux/">Linux Version</a>
  •
  <a href="https://github.com/DeveloperMezba">Developer</a>
</p>

---

## About

**Mezba Download Manager**, also known as **MDM**, is a modern download manager for Windows designed to provide a simple, fast, and convenient way to manage file and media downloads.

MDM combines a desktop application with browser integration so downloads can be sent directly from supported browsers to the download manager.

The project is actively developed with a focus on reliable downloading, clear progress information, resumable downloads, browser integration, media downloading, and a clean Windows experience.

---

## Features

### Download Management

- File download management
- Multiple download queue
- Resumable direct-file downloads
- Download progress monitoring
- Retry and completion handling
- Background downloading
- Downloads can continue after the main MDM window is closed
- Compact progress windows
- Clear download status information

### Media Downloads

MDM supports several types of media downloads, including:

- MP4 video
- MKV video
- Audio downloads
- Playlists
- Supported online media
- Media processing using required background components

Availability may depend on the website and the type of content being downloaded.

### Google Drive

MDM includes support for downloading supported public Google Drive files.

Current Google Drive support is primarily intended for public single-file downloads.

### Browser Integration

MDM includes a browser companion extension and Windows native messaging integration.

Supported Chromium-based browsers include:

- Google Chrome
- Brave
- Microsoft Edge
- Chromium
- Vivaldi

Firefox integration is also available, although the current Firefox extension may need to be loaded manually depending on the version being used.

---

## Download

The recommended way to install Mezba Download Manager is through the official GitHub Releases page.

### [Download the Latest Windows Release](https://github.com/DeveloperMezba/mezba-download-manager-windows/releases/latest)

Download the Windows x64 installer from the **Assets** section of the latest release.

The installer filename may look similar to:

```text
Mezba-Download-Manager-x.x.x-Windows-x64-Setup.exe
```

Always download MDM from this official repository.

---

## System Requirements

- Windows 10 or Windows 11
- 64-bit Windows
- Internet connection
- Sufficient free storage space for downloads
- Additional temporary storage may be required during media processing

An internet connection is particularly important during the initial setup because MDM may need to download required components.

---

## Installation

1. Open the [Releases](https://github.com/DeveloperMezba/mezba-download-manager-windows/releases) page.
2. Open the latest release.
3. Download the Windows x64 setup file from the **Assets** section.
4. Close any older MDM installation before installing an update.
5. Run the installer.
6. Complete the installation.
7. Launch **Mezba Download Manager**.
8. Allow the initial setup to download any required components.
9. Configure browser integration from the application's browser setup section.

---

## Windows SmartScreen

Current builds may not yet be digitally code-signed.

Because of this, Windows SmartScreen may display a warning when you run the installer.

Make sure the installer was downloaded directly from:

```text
https://github.com/DeveloperMezba/mezba-download-manager-windows
```

If Windows SmartScreen appears, verify that the installer came from the official GitHub repository before continuing.

---

## Browser Setup

After installing MDM, configure the browser companion extension so downloads can be transferred from your browser to the desktop application.

For Chromium-based browsers:

1. Open Mezba Download Manager.
2. Open the browser setup or integration section.
3. Follow the extension installation instructions.
4. Install or load the MDM browser extension.
5. Allow MDM's native browser integration when required.
6. Reload the browser extension after updating MDM if necessary.
7. Restart the browser if integration does not become active immediately.

Supported Chromium-based browsers include:

- Google Chrome
- Brave
- Microsoft Edge
- Chromium
- Vivaldi

---

## Firefox

Firefox support is available separately from Chromium browser integration.

Depending on the current MDM release, the Firefox companion may require manual installation or temporary loading.

A permanently signed Firefox extension may be provided in a future release.

---

## Updates

MDM includes an update system designed to keep both the application and its required download components up to date.

Inside Mezba Download Manager, use:

```text
Check for updates
```

The update system can handle two main types of updates.

### Application Update

Checks for a newer version of Mezba Download Manager from the official GitHub repository.

### Download Tools and Components

Checks supported background components used by MDM and updates them when appropriate.

Components used by the Windows edition may include tools such as:

- FFmpeg
- ffprobe
- Deno
- yt-dlp
- Other required downloading or media-processing components

Updates are performed when requested by the user.

Where supported, update downloads may be verified before installation and MDM attempts to preserve existing application data during the update process.

---

## FFmpeg, yt-dlp, and Deno

Normal users should not need to manually install FFmpeg, ffprobe, yt-dlp, Deno, Python, Java, or other development dependencies simply to use the Windows version.

MDM is designed to manage its required download and media-processing components automatically where possible.

This helps make installation simpler for normal Windows users.

---

## Download Queue

MDM can manage multiple downloads through its download queue.

This allows you to:

- Add multiple downloads
- Track download progress
- Manage active downloads
- Retry failed downloads
- Continue supported downloads
- Keep downloads running without keeping the main application window open

---

## Resume Support

Supported direct-file downloads can be resumed when the server allows partial or range downloads.

Resume capability can vary depending on:

- The server
- The website
- The download source
- The file type
- Whether the server supports range requests

Some media downloads may use different resume behavior depending on the source.

---

## Download Completion

MDM distinguishes between the transfer reaching 100% and the entire download process actually being finished.

Some media downloads require additional processing after the transfer reaches 100%.

For example, MDM may need to:

- Merge audio and video streams
- Process downloaded media
- Convert or finalize a file
- Run FFmpeg processing
- Verify the completed output

The download should only be considered finished after all required processing has completed successfully.

---

## Background Downloads

MDM is designed so supported downloads can continue even when the main application window is closed.

The exact behavior may depend on:

- The type of download
- The download component being used
- Windows power settings
- Whether Windows enters sleep mode
- Whether the computer is shut down

Windows sleep or shutdown can still interrupt active downloads.

---

## Known Limitations

Mezba Download Manager is still under active development.

Current limitations may include:

- The Windows build may not yet be digitally signed.
- Some websites use DRM or anti-bot systems that prevent normal downloading.
- Content requiring account authentication may not always be accessible.
- Some websites may change their internal systems and temporarily break media downloading.
- Google Drive support currently focuses mainly on supported public file downloads.
- Google Drive folder downloading may not be fully supported.
- Firefox browser integration may require manual setup.
- Windows sleep or shutdown can interrupt downloads.
- Some browser and Windows combinations may require additional real-world testing.
- Some servers do not support resumable downloads.
- Website-specific restrictions may prevent certain downloads.

MDM is not intended to bypass DRM, account restrictions, website security systems, or access controls.

---

## Troubleshooting

### Browser sends a download but nothing starts

Try the following:

1. Make sure Mezba Download Manager is installed.
2. Open MDM at least once.
3. Re-run the browser integration setup.
4. Reload the browser extension.
5. Restart your browser.
6. Restart MDM.
7. Try the download again.

### Brave or Chrome integration is not working

Reload the MDM browser extension and verify that browser integration has been completed correctly.

If you recently updated MDM, restart both MDM and the browser.

### Download reaches 100% but does not immediately show Completed

Some media downloads require post-processing after the transfer reaches 100%.

Wait until MDM finishes processing, merging, converting, or finalizing the file.

### Media conversion fails

If media processing fails, MDM attempts to preserve downloaded files where possible so the original downloaded data is not unnecessarily lost.

### Download cannot be resumed

The download server may not support resumable or range-based downloads.

In that situation, the file may need to restart from the beginning.

### A website refuses to download

Some websites may require:

- Login credentials
- Browser cookies
- Anti-bot verification
- DRM-protected playback
- Website-specific handling
- Additional authentication

Not every website or protected stream can be supported.

---

## Reporting Bugs

If something does not work, please report it through GitHub Issues.

### [Open an Issue](https://github.com/DeveloperMezba/mezba-download-manager-windows/issues)

When reporting a problem, please include as much of the following information as possible:

- MDM version
- Windows version
- Browser name
- Browser version
- Type of download
- Website or download source when appropriate
- What you expected to happen
- What actually happened
- Error message
- Screenshot if available
- Steps needed to reproduce the problem

Detailed reports make bugs much easier to reproduce and fix.

---

## Feature Requests

Ideas and suggestions are welcome.

If you have an idea for a new feature or improvement, open an issue and describe:

- What you would like MDM to do
- Why the feature would be useful
- How you expect it to work

### [Request a Feature](https://github.com/DeveloperMezba/mezba-download-manager-windows/issues)

---

## Project Status

MDM for Windows is under **active development**.

The project is continuously being improved with a focus on:

- Download reliability
- Browser integration
- Better download status reporting
- Improved error handling
- Media downloading
- Update management
- Windows integration
- User experience
- Performance
- Stability
- Download queue improvements
- Better resume support

This repository should currently be considered an actively developed project rather than a completely finished final product.

---

## Linux Version

Mezba Download Manager also has a separate Linux edition.

Visit the DeveloperMezba GitHub profile to find the Linux version:

### [DeveloperMezba on GitHub](https://github.com/DeveloperMezba)

---

## Official Repository

The official Windows repository is:

```text
https://github.com/DeveloperMezba/mezba-download-manager-windows
```

Please avoid downloading modified or unofficial copies from unknown sources.

---

## Contributing

Contributions, bug reports, testing feedback, and useful suggestions are welcome.

If you would like to contribute:

1. Fork the repository.
2. Create a new branch for your change.
3. Make your changes.
4. Test the changes carefully.
5. Submit a pull request with a clear explanation.

For major changes, opening an issue first is recommended so the idea can be discussed before implementation.

---

## Developer

Created and maintained by **DeveloperMezba**.

GitHub:

### [@DeveloperMezba](https://github.com/DeveloperMezba)

---

## Support the Project

If Mezba Download Manager is useful to you:

- Star the repository
- Report bugs
- Suggest improvements
- Share the project
- Contribute code or testing feedback

Every contribution helps improve MDM.

---

<p align="center">
  <strong>Mezba Download Manager</strong><br>
  Download smarter on Windows.
</p>

<p align="center">
  ⭐ If MDM is useful to you, consider starring the repository.
</p>
