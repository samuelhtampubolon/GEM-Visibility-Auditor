"""Uji smoke .exe hasil PyInstaller. Aktif bila GEM_EXE_PATH menunjuk ke file .exe/biner."""

import os
import subprocess

import pandas as pd
import pytest

EXE = os.environ.get("GEM_EXE_PATH")
pytestmark = pytest.mark.skipif(not EXE, reason="set GEM_EXE_PATH untuk menguji .exe")


def test_exe_demo_run(tmp_path):
    out = tmp_path / "exe_out"
    p = subprocess.run([EXE, "--demo", "--out", str(out)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600, stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stdout + p.stderr
    for name in ("responses.csv", "summary.csv", "share_of_voice.png", "report.html", "dashboard_data.json"):
        assert (out / name).stat().st_size > 0, name
    assert len(pd.read_csv(out / "summary.csv", encoding="utf-8-sig")) == 11


def test_exe_version_and_questions():
    p = subprocess.run([EXE, "--list-questions"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, stdin=subprocess.DEVNULL)
    assert p.returncode == 0 and len(p.stdout.strip().splitlines()) == 30
