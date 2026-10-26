#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Peluncur dashboard Streamlit agar bisa dibundel menjadi satu .exe.

Jalankan biasa : python dashboard_launcher.py   (sama dengan: streamlit run streamlit_app.py)
Build .exe     :
  pip install pyinstaller streamlit pandas matplotlib requests
  pyinstaller --onefile --name GEM-Dashboard --collect-all streamlit --copy-metadata streamlit --add-data "streamlit_app.py:." --add-data "gem_visibility_auditor.py:." --hidden-import gem_visibility_auditor dashboard_launcher.py
  Hasil: dist/GEM-Dashboard.exe, membuka http://localhost:8501 di browser.
"""

import os
import sys
from pathlib import Path


def app_path() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / "streamlit_app.py")


def main() -> None:
    from streamlit.web import cli as stcli

    port = os.environ.get("GEM_DASHBOARD_PORT", "8501")
    sys.argv = [
        "streamlit", "run", app_path(),
        "--global.developmentMode=false",
        "--server.port", port,
        "--server.headless", os.environ.get("GEM_DASHBOARD_HEADLESS", "false"),
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
