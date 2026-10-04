# Third-party components

MDM's own Python/JavaScript/C/installer source is MIT-licensed. Separate components retain their upstream licenses. The installer preserves Python's license and wheel license metadata inside its private runtime. Tcl/Tk license texts remain in runtime/tcl.

Python 3.13.15 and Tcl/Tk are obtained from the official Python Windows distribution. Source and license: https://www.python.org/downloads/release/python-31315/ and https://docs.python.org/3/license.html. Tcl/Tk: https://www.tcl-lang.org/software/tcltk/ .

Bundled Python packages (see build/python-packages-lock.json for exact archive URLs and SHA-256 values):

| Package | Version | Source / license reference |
|---|---|---|
| brotli | 1.2.0 | https://pypi.org/project/brotli/1.2.0/ |
| idna | 3.20 | https://pypi.org/project/idna/3.20/ |
| mutagen | 1.48.1 | https://pypi.org/project/mutagen/1.48.1/ |
| tqdm | 4.70.1 | https://pypi.org/project/tqdm/4.70.1/ |
| charset-normalizer | 3.5.1 | https://pypi.org/project/charset-normalizer/3.5.1/ |
| filelock | 4.0.4 | https://pypi.org/project/filelock/4.0.4/ |
| yt-dlp-ejs | 0.8.0 | https://pypi.org/project/yt-dlp-ejs/0.8.0/ |
| yt-dlp | 2026.8.19 | https://pypi.org/project/yt-dlp/2026.8.19/ |
| requests | 2.34.2 | https://pypi.org/project/requests/2.34.2/ |
| beautifulsoup4 | 4.15.0 | https://pypi.org/project/beautifulsoup4/4.15.0/ |
| certifi | 2026.7.22 | https://pypi.org/project/certifi/2026.7.22/ |
| PySocks | 1.7.1 | https://pypi.org/project/PySocks/1.7.1/ |
| typing-extensions | 4.16.0 | https://pypi.org/project/typing-extensions/4.16.0/ |
| websockets | 17.1 | https://pypi.org/project/websockets/17.1/ |
| urllib3 | 2.8.0 | https://pypi.org/project/urllib3/2.8.0/ |
| gdown | 6.4.0 | https://pypi.org/project/gdown/6.4.0/ |
| pycryptodomex | 3.23.0 | https://pypi.org/project/pycryptodomex/3.23.0/ |
| soupsieve | 2.10 | https://pypi.org/project/soupsieve/2.10/ |

Python wheel archives include the package Python source and license notices. Native extensions use upstream redistributable binaries under their respective licenses. Mutagen's corresponding upstream source is included under third-party-source, alongside the package's license metadata.

FFmpeg and Deno binaries are **not embedded** in this installer. Setup downloads verified packages from their upstream releases into the user's installation. Their original license/README texts are retained under tools/licenses. Current download versions and hashes are pinned in source/media-tools-lock.json.

- FFmpeg source and licensing: https://ffmpeg.org/download.html and https://ffmpeg.org/legal.html
- Gyan Windows build details: https://www.gyan.dev/ffmpeg/builds/
- Deno source/license: https://github.com/denoland/deno
- yt-dlp source/license: https://github.com/yt-dlp/yt-dlp
- gdown source/license: https://github.com/wkentaro/gdown
- NSIS installer system: https://nsis.sourceforge.io/License

MDM is not affiliated with Internet Download Manager, Microsoft, Google, Meta, Python, or these component maintainers.
