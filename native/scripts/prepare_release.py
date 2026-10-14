"""Verify downloaded CI artifacts before copying them into a release directory."""
import argparse
import hashlib
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

CHECKS = ("windowActivated", "mouseSelectClip", "mouseMoveClip", "mouseTrimClip",
          "keyboardSplit", "keyboardUndo", "keyboardRedo", "renderedPlaybackFrames",
          "previewPixmapVisible", "screenshotCaptured", "windowVisible")


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def inspect_artifact(root,system):
    line=(root/"dist"/"SHA256SUMS.txt").read_text(encoding="utf-8").strip()
    expected,name=line.split(maxsplit=1)
    if Path(name).name!=name:
        raise ValueError("Invalid checksum manifest filename")
    archive=root/"dist"/name
    if digest(archive)!=expected:
        raise ValueError("CI artifact checksum mismatch: "+name)
    report=json.loads((root/"test-output"/"media.json").read_text(encoding="utf-8"))
    if any(report.get(check) is not True for check in CHECKS):
        raise ValueError("Packaged desktop verification did not pass: "+system)
    if report.get("playerError") or report.get("decodedVideoFrameCount",0)<3:
        raise ValueError("Packaged media playback was not verified")
    if system=="linux":
        with tarfile.open(archive,"r:gz") as tar:
            member=tar.getmember("PalmierProLinux/PalmierProLinux")
            if not member.isfile() or not member.mode&0o111:
                raise ValueError("Linux executable permissions are missing")
            with tar.extractfile(member) as file:
                header=file.read(64)
            if header[:6]!=b"\x7fELF\x02\x01" or int.from_bytes(header[18:20],"little")!=62:
                raise ValueError("Linux executable is not x86_64 ELF")
    else:
        with zipfile.ZipFile(archive) as zip:
            with zip.open("PalmierProWindows/PalmierProWindows.exe") as file:
                if file.read(2)!=b"MZ":
                    raise ValueError("Windows executable header is invalid")
    return archive,expected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--linux",required=True,type=Path)
    parser.add_argument("--windows",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    payloads=[(system,root,*inspect_artifact(root,system)) for system,root in [("linux",args.linux),("windows",args.windows)]]
    args.output.mkdir(exist_ok=False)
    sums=[]
    for system,root,archive,sha in payloads:
        shutil.copyfile(archive,args.output/archive.name)
        shutil.copyfile(root/"test-output"/"media.json",args.output/(system+"-verification.json"))
        shutil.copyfile(root/"test-output"/"media.png",args.output/(system+"-desktop.png"))
        sums.append(sha+"  "+archive.name)
    (args.output/"SHA256SUMS.txt").write_text("\n".join(sums)+"\n",encoding="utf-8")
    print(json.dumps(dict(verified=True,output=str(args.output),sha256=sums),indent=2))


if __name__=="__main__":
    main()
