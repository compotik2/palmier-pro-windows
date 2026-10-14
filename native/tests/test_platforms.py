import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from palmier.platforms import text_font,desktop_name
from palmier.media import parse_ffmpeg_major,filter_file_option


class PlatformTests(unittest.TestCase):
    def test_modern_and_ubuntu_ffmpeg_version_parsing(self):
        self.assertEqual(parse_ffmpeg_major("ffmpeg version 4.4.2-0ubuntu0.22.04.1"),4)
        self.assertEqual(parse_ffmpeg_major("ffmpeg version 9.0.2-full_build-www.gyan.dev"),9)
        for value in ("ffmpeg version 3.4", "ffmpeg version 4.1", "garbage"):
            with self.assertRaises(ValueError):
                parse_ffmpeg_major(value)

    def test_filter_file_option_matches_supported_cli_generation(self):
        for version,expected in [(4,"-filter_complex_script"),(6,"-filter_complex_script"),(7,"-/filter_complex"),(9,"-/filter_complex")]:
            filter_file_option.cache_clear()
            response=subprocess.CompletedProcess([],0,stdout=f"ffmpeg version {version}.4.0".encode())
            with patch("palmier.media.run",return_value=response):
                self.assertEqual(filter_file_option("test-binary"),expected)
        filter_file_option.cache_clear()

    def test_font_override_works_with_linux_paths(self):
        with tempfile.TemporaryDirectory() as root:
            font=Path(root)/"font.ttf"
            font.write_bytes(b"test-font")
            with patch.dict(os.environ,{"PALMIER_FONT_PATH":str(font)}):
                self.assertEqual(text_font("Linux"),font)
            with patch.dict(os.environ,{"PALMIER_FONT_PATH":"missing.ttf"}):
                with self.assertRaises(ValueError):
                    text_font("Linux")

    def test_linux_font_selection_does_not_require_windows(self):
        with patch.dict(os.environ,{"PALMIER_FONT_PATH":""}),patch("pathlib.Path.is_file",side_effect=lambda:True):
            self.assertIn("liberation",str(text_font("Linux")))

    def test_current_host_name_is_desktop_specific(self):
        self.assertIn(desktop_name(),("Palmier Pro Windows","Palmier Pro Linux"))
