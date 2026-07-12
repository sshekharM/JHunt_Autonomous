"""
Build jHANS_Setup.exe using PyInstaller.

Run this script on Windows (or the target platform) to produce the installer binary:
    python build_exe.py

Requirements:
    pip install pyinstaller

The output will be at:
    installer/dist/jHANS_Setup.exe
"""
import subprocess
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # Generate icon.ico if it doesn't exist
    icon_path = os.path.join(_HERE, "assets", "icon.ico")
    if not os.path.exists(icon_path):
        print("Generating icon.ico...")
        subprocess.run(
            [sys.executable, os.path.join(_HERE, "assets", "create_icon.py")],
            check=True
        )

    print("Running PyInstaller...")
    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            os.path.join(_HERE, "jhans_installer.spec"),
        ],
        cwd=_HERE,
        check=False,
    )

    if result.returncode == 0:
        dist_path = os.path.join(_HERE, "dist", "jHANS_Setup.exe")
        print(f"\nBuild successful!")
        print(f"Output: {dist_path}")
    else:
        print(f"\nBuild FAILED (exit code {result.returncode})")
        print("Check the output above for errors.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
