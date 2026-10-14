import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent


def main():
    vendor=ROOT/"vendor"
    notices=vendor/"licenses"
    notices.mkdir(parents=True,exist_ok=True)
    license_sources = {
        "Qt-LGPL-3.0-only.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/LGPL-3.0-only.txt",
        "FFmpeg-LGPLv2.1.txt": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1/COPYING.LGPLv2.1",
    }
    for name, url in license_sources.items():
        file = notices / name
        if not file.exists():
            with urllib.request.urlopen(url, timeout=30) as response:
                file.write_bytes(response.read())
    inventory=[]
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get("Name","unknown")
        inventory.append(dict(name=name,version=dist.version))
        for file in dist.files or []:
            if any(key in str(file).lower() for key in ("license","copying","notice")):
                source=Path(dist.locate_file(file))
                if source.is_file():
                    destination=notices/name/str(file)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,destination)
    for file in (Path(sys.base_prefix)/"LICENSE.txt",Path(sys.base_prefix)/"LICENSE"):
        if file.is_file():
            shutil.copyfile(file,notices/"Python-LICENSE.txt")
    (vendor/"dependency-inventory.json").write_text(json.dumps(inventory,indent=2),encoding="utf-8")
    if shutil.which("ffmpeg"):
        version=subprocess.run([shutil.which("ffmpeg"),"-version"],capture_output=True,text=True,check=True).stdout
        (vendor/"ffmpeg-validation-environment.txt").write_text(version,encoding="utf-8")
    import PySide6
    qt=Path(PySide6.__file__).parent
    binaries=[]
    for name in ("avutil-59.dll", "avcodec-61.dll", "avformat-61.dll", "swresample-5.dll", "swscale-8.dll"):
        binaries.extend(["--add-binary",str(qt/name)+";PySide6"])
    subprocess.run([sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir","--windowed",*binaries,
        "--name","PalmierProWindows","--add-data",str(REPO/"LICENSE")+";.",
        "--add-data",str(REPO/"NOTICE")+";.","--add-data",str(ROOT/"README.md")+";.",
        "--add-data",str(ROOT/"docs")+";docs","--add-data",str(vendor)+";vendor",str(ROOT/"main.py")],cwd=ROOT,check=True)
    application=ROOT/"dist"/"PalmierProWindows"
    for file in (REPO/"LICENSE",REPO/"NOTICE",ROOT/"README.md"):
        shutil.copyfile(file,application/file.name)
    archive=ROOT/"dist"/"PalmierProWindows-0.2.0-win-x64-portable.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zip:
        for file in sorted(application.rglob("*")):
            if file.is_file():
                zip.write(file,file.relative_to(application.parent))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent/"SHA256SUMS.txt").write_text(digest+"  "+archive.name+"\n",encoding="utf-8")
    print(json.dumps(dict(exe=str(application/"PalmierProWindows.exe"),archive=str(archive),sha256=digest),indent=2))


if __name__=="__main__":
    main()
