"""Simulasi Google Colab: SELURUH isi file ditempel ke SATU sel notebook lalu dijalankan."""

import os

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")


def test_whole_file_in_one_cell(root, tmp_path):
    source = (root / "gem_visibility_auditor.py").read_text(encoding="utf-8")
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(source))
    # Sel kedua memeriksa hasil, seperti pengguna melihat panel Files di Colab.
    nb.cells.append(nbformat.v4.new_code_cell(
        "import glob, os\n"
        "dirs = sorted(glob.glob('gem_audit_output/audit_*'))\n"
        "dirs = [d for d in dirs if os.path.isdir(d)]\n"
        "assert dirs, 'folder hasil tidak ada'\n"
        "files = sorted(os.listdir(dirs[-1]))\n"
        "print('FILES', files)\n"
        "assert 'report.html' in files and 'share_of_voice.png' in files and 'responses.csv' in files\n"
        "assert glob.glob('gem_audit_output/audit_*.zip')\n"
    ))
    os.environ["GEM_NONINTERACTIVE"] = "1"
    try:
        client = nbclient.NotebookClient(nb, timeout=300, kernel_name="python3",
                                         resources={"metadata": {"path": str(tmp_path)}})
        client.execute()
    finally:
        os.environ.pop("GEM_NONINTERACTIVE", None)
    out_text = "".join(o.get("text", "") for o in nb.cells[0].outputs if o.get("output_type") == "stream")
    assert "mode notebook" in out_text and "Danau Toba: share of AI voice" in out_text
    images = [o for o in nb.cells[0].outputs if "image/png" in o.get("data", {})]
    assert len(images) == 4, "keempat grafik harus tampil inline"
    assert "FILES" in "".join(o.get("text", "") for o in nb.cells[1].outputs)
