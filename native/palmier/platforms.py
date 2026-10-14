import os
import platform
from pathlib import Path


def desktop_name():
    return "Palmier Pro " + ("Windows" if os.name == "nt" else "Linux")


def ui_font():
    return "Segoe UI" if os.name == "nt" else "DejaVu Sans"


def text_font(system=None):
    override = os.environ.get("PALMIER_FONT_PATH")
    if override:
        result = Path(override)
        if not result.is_absolute() or not result.is_file():
            raise ValueError("PALMIER_FONT_PATH must identify an existing absolute font path")
        return result
    system = system or platform.system()
    if system == "Windows":
        candidates = [Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"/"arial.ttf"]
    else:
        candidates = [Path(name) for name in (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        )]
    result = next((file for file in candidates if file.is_file()), None)
    if result is None:
        raise ValueError("No text font found. Install fonts-liberation/fonts-dejavu-core or set PALMIER_FONT_PATH")
    return result
