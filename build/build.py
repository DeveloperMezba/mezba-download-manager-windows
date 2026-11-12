import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

RUNTIME_PTH = (
    "python313.zip\n"
    "../app\n"
    "DLLs\n"
    "Lib/site-packages\n"
    "import site\n"
)


def print_step(message):
    print(f"=== {message} ===", flush=True)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_verified(item, cache_dir):
    target = cache_dir / item["name"]
    if not target.exists() or sha256_of(target) != item["sha256"]:
        print(f"Downloading {item['name']}...", flush=True)
        urllib.request.urlretrieve(item["url"], target)
        actual = sha256_of(target)
        if actual != item["sha256"]:
            target.unlink()
            raise SystemExit(f"Checksum mismatch for {item['name']}: {actual}")
    else:
        print(f"Using cached {item['name']}", flush=True)
    return target


def extract_msi(msi_path, out_dir, msiextract, is_windows):
    out_dir.mkdir(parents=True, exist_ok=True)
    if is_windows:
        subprocess.run(
            ["msiexec.exe", "/a", str(msi_path), "/qn", f"TARGETDIR={out_dir}"],
            check=True,
        )
    else:
        subprocess.run([msiextract, "-C", str(out_dir), str(msi_path)], check=True)


def copy_tree(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def compile_launcher(cc, windres, build_dir, out_exe):
    res_obj = build_dir / "launcher_res.o"
    subprocess.run(
        [windres, "launcher.rc", "-O", "coff", "-o", str(res_obj)],
        cwd=build_dir,
        check=True,
    )
    subprocess.run(
        [
            cc, "launcher.c", str(res_obj), "-o", str(out_exe),
            "-municode", "-mwindows", "-static", "-s", "-lshell32",
        ],
        cwd=build_dir,
        check=True,
    )
    if not out_exe.exists():
        raise SystemExit(f"Launcher compile produced no output: {out_exe}")


def stage_runtime(payload_dir, embed_zip, tcltk_dir):
    runtime = payload_dir / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(embed_zip) as archive:
        archive.extractall(runtime)
    copy_tree(tcltk_dir / "DLLs", runtime / "DLLs")
    copy_tree(tcltk_dir / "tcl", runtime / "tcl")
    copy_tree(tcltk_dir / "Lib" / "tkinter", runtime / "Lib" / "tkinter")
    pth_files = list(runtime.glob("python3*._pth"))
    if not pth_files:
        raise SystemExit("Embeddable runtime has no python3*._pth file")
    pth_files[0].write_text(RUNTIME_PTH, encoding="utf-8")
    return runtime


def stage_wheels(lock_path, cache_dir, site_packages):
    site_packages.mkdir(parents=True, exist_ok=True)
    items = json.loads(lock_path.read_text(encoding="utf-8"))
    for item in items:
        wheel = fetch_verified(item, cache_dir)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(site_packages)
    print(f"Installed {len(items)} pinned wheels into the private runtime", flush=True)


def stage_app(source_dir, payload_dir, root):
    app_dir = payload_dir / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    shutil.copytree(
        source_dir,
        app_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("README.md", "LICENSE"):
        src = root / name
        if src.exists():
            shutil.copy2(src, payload_dir / name)


def main():
    parser = argparse.ArgumentParser(description="MDM Windows Build Script")
    parser.add_argument("--version", default="0.1.3", help="Application version")
    parser.add_argument("--cc", default=None, help="C compiler for the launchers")
    parser.add_argument("--windres", default=None, help="windres executable")
    parser.add_argument("--makensis", default=None, help="Path to makensis executable")
    parser.add_argument("--msiextract", default="msiextract", help="msiextract executable (Linux)")
    parser.add_argument("--tcltk-extracted", default=None, help="Pre-extracted Tcl/Tk directory")
    parser.add_argument("--build-cache", default=None, help="Download cache directory")
    args = parser.parse_args()

    is_windows = platform.system() == "Windows"
    cc = args.cc or ("gcc" if is_windows else "x86_64-w64-mingw32-gcc")
    windres = args.windres or ("windres" if is_windows else "x86_64-w64-mingw32-windres")
    makensis = args.makensis or ("makensis.exe" if is_windows else "makensis")

    root = Path(__file__).parent.parent.absolute()
    build_dir = root / "build"
    source_dir = root / "source"
    dist_dir = root / "dist"
    payload_dir = dist_dir / "payload"
    cache_dir = Path(args.build_cache).absolute() if args.build_cache else root / "build-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if payload_dir.exists():
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    print_step("Step 1: Downloading and verifying pinned runtime assets")
    runtime_items = json.loads(
        (build_dir / "python-runtime-lock.json").read_text(encoding="utf-8")
    )
    downloaded = {}
    for item in runtime_items:
        downloaded[item["name"]] = fetch_verified(item, cache_dir)

    print_step("Step 2: Preparing the Tcl/Tk extraction")
    if args.tcltk_extracted:
        tcltk_dir = Path(args.tcltk_extracted).absolute()
    else:
        tcltk_dir = cache_dir / "tcltk"
        if tcltk_dir.exists():
            shutil.rmtree(tcltk_dir)
        tcltk_dir.mkdir(parents=True)
        extract_msi(downloaded["tcltk.msi"], tcltk_dir, args.msiextract, is_windows)
    for required in ("DLLs", "tcl", "Lib/tkinter"):
        if not (tcltk_dir / required).exists():
            raise SystemExit(f"Tcl/Tk extraction is missing {required} in {tcltk_dir}")

    print_step("Step 3: Assembling the private runtime")
    runtime = stage_runtime(payload_dir, downloaded["python-3.13.15-embed-amd64.zip"], tcltk_dir)

    print_step("Step 4: Installing pinned wheels into the private runtime")
    stage_wheels(build_dir / "python-packages-lock.json", cache_dir, runtime / "Lib" / "site-packages")

    print_step("Step 5: Staging the app and launchers")
    stage_app(source_dir, payload_dir, root)
    compile_launcher(cc, windres, build_dir, payload_dir / "MDM.exe")
    compile_launcher(cc, windres, build_dir, payload_dir / "MDMNativeHost.exe")

    print_step("Step 6: Creating the NSIS Windows installer")
    output_installer = dist_dir / f"Mezba-Download-Manager-{args.version}-Windows-x64-Setup.exe"
    nsis_cmd = [
        makensis,
        "/V2",
        f"/DVERSION={args.version}",
        f"/DPAYLOAD={payload_dir}",
        f"/DOUTPUT={output_installer}",
        "installer.nsi",
    ]
    subprocess.run(nsis_cmd, cwd=build_dir, check=True)
    if not output_installer.exists():
        raise SystemExit(f"NSIS did not produce {output_installer}")

    sums_path = dist_dir / "SHA256SUMS"
    sums_path.write_text(
        f"{sha256_of(output_installer)}  {output_installer.name}\n", encoding="utf-8"
    )
    print_step(f"Build complete! Installer saved at: {output_installer}")


if __name__ == "__main__":
    main()
