import os
import sys
import subprocess
import argparse
import pathlib

def main():
    parser = argparse.ArgumentParser(description="MDM Windows Build Script")
    parser.add_argument("--makensis", default="makensis.exe", help="Path to makensis executable")
    parser.add_argument("--version", default="0.1.3", help="Application version")
    args = parser.parse_args()

    # প্রজেক্টের রুট এবং বিভিন্ন ফোল্ডারের পাথ ডিফাইন করা
    root = pathlib.Path(__file__).parent.parent.absolute()
    build_dir = root / "build"
    source_dir = root / "source"
    dist_dir = root / "dist"
    payload_dir = dist_dir / "payload"
    
    # payload ফোল্ডার না থাকলে তৈরি করে নেওয়া
    payload_dir.mkdir(parents=True, exist_ok=True)

    print("=== Step 1: Building MDM.exe using PyInstaller ===", flush=True)
    
    # PyInstaller কমান্ড যা সরাসরি dist/payload ফোল্ডারে MDM.exe তৈরি করবে
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "MDM",
        "--icon", str(build_dir / "mdm.ico"),
        "--distpath", str(payload_dir),
        str(source_dir / "mdm.py")
    ]
    
    subprocess.run(pyinstaller_cmd, check=True)

    # নিশ্চিত করা যে MDM.exe ফাইলটি সঠিকভাবে তৈরি হয়েছে কি না
    exe_path = payload_dir / "MDM.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"Critical Error: PyInstaller failed to generate {exe_path}")
    
    print(f"Successfully generated: {exe_path}", flush=True)

    print("=== Step 2: Creating NSIS Windows Installer ===", flush=True)
    
    output_installer = dist_dir / f"Mezba-Download-Manager-{args.version}-Windows-x64-Setup.exe"
    
    # NSIS (makensis) রান করার কমান্ড
    nsis_cmd = [
        args.makensis,
        "/V2",
        f"/DVERSION={args.version}",
        f"/DPAYLOAD={payload_dir}",
        f"/DOUTPUT={output_installer}",
        "installer.nsi"
    ]
    
    print(f"Running NSIS from {build_dir}...", flush=True)
    subprocess.run(nsis_cmd, cwd=build_dir, check=True)
    
    print(f"=== Build Complete! Installer saved at: {output_installer} ===")

if __name__ == '__main__':
    main()
