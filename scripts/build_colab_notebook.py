#!/usr/bin/env python3
"""Bangun GEM_Visibility_Auditor_Colab.ipynb: satu sel kode berisi SELURUH gem_visibility_auditor.py.

Pakai: python scripts/build_colab_notebook.py
Tes tests/test_notebook_colab.py memastikan notebook selalu sama dengan file .py.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gem_visibility_auditor.py"
OUT = ROOT / "GEM_Visibility_Auditor_Colab.ipynb"

INTRO = """# GEM Visibility Auditor (Google Colab)

Audit **share of AI voice**: berapa kali Danau Toba disebut LLM dibanding Bali, Labuan Bajo, dan destinasi lain.

1. (Opsional) Klik ikon kunci di panel kiri (**Secrets**), tambahkan `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
   dan/atau `OPENAI_API_KEY`, aktifkan *Notebook access*.
2. Jalankan sel kode di bawah (**Shift+Enter**). Tanpa kunci, Anda ditanya kunci atau mode demo (simulasi) berjalan.
3. Tabel dan grafik tampil di bawah sel; hasil lengkap diunduh sebagai `.zip`.

Pengaturan (model, bahasa, pengulangan) ada di `NOTEBOOK_SETTINGS` di bagian atas sel.
Sel ini identik dengan isi `gem_visibility_auditor.py` di repo."""


def build() -> dict:
    code = SRC.read_text(encoding="utf-8")
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "colab": {"provenance": [], "name": "GEM_Visibility_Auditor_Colab.ipynb"},
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
        },
        "cells": [
            {"cell_type": "markdown", "id": "intro", "metadata": {}, "source": INTRO.splitlines(keepends=True)},
            {"cell_type": "code", "id": "audit", "metadata": {}, "execution_count": None, "outputs": [],
             "source": code.splitlines(keepends=True)},
        ],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ditulis: {OUT.name}")
