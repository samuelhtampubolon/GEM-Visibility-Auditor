"""Uji end-to-end CLI sebagai proses terpisah (seperti pengguna menjalankannya)."""

import json
import os
import subprocess
import sys

import pandas as pd

import gem_visibility_auditor as gva

OUTPUTS = ["responses.csv", "mentions.csv", "summary.csv", "sov_by_language.csv", "sov_by_model.csv",
           "sov_by_category.csv", "share_of_voice.png", "sov_by_language.png", "sov_by_model.png",
           "mention_rate.png", "report.html", "dashboard_data.json", "responses.jsonl"]


def run_cli(root, *args, env=None, timeout=300):
    e = dict(os.environ)
    e.update(env or {})
    e["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, str(root / "gem_visibility_auditor.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", env=e, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def test_demo_end_to_end(root, tmp_path):
    out = tmp_path / "demo"
    p = run_cli(root, "--demo", "--out", str(out), "--zip")
    assert p.returncode == 0, p.stdout + p.stderr
    for name in OUTPUTS:
        assert (out / name).is_file() and (out / name).stat().st_size > 0, name
    assert (tmp_path / "demo.zip").is_file()
    s = pd.read_csv(out / "summary.csv", encoding="utf-8-sig")
    assert len(s) == 11 and abs(s["share_of_voice_pct"].sum() - 100) < 0.1
    r = pd.read_csv(out / "responses.csv", encoding="utf-8-sig")
    assert len(r) == 60 and set(r["status"]) == {"ok"}  # 2 model x 15 topik x 2 bahasa
    report = (out / "report.html").read_text(encoding="utf-8")
    assert "SIMULASI" in report and "data:image/png;base64," in report and chr(0x2014) not in report
    assert "Danau Toba: share of AI voice" in p.stdout
    dash = json.loads((out / "dashboard_data.json").read_text(encoding="utf-8"))
    assert len(dash["responses"]) == 60 and dash["config"]["focus"] == "danau_toba"


def test_real_http_path_through_cli(root, tmp_path, mock_server):
    """Jalur API nyata (requests + parsing) untuk 3 provider, 90 permintaan."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-test", "GEMINI_API_KEY": "g-test", "OPENAI_API_KEY": "sk-test",
           "GEM_ANTHROPIC_BASE_URL": mock_server.base, "GEM_GEMINI_BASE_URL": mock_server.base + "/v1beta",
           "GEM_OPENAI_BASE_URL": mock_server.base + "/v1", "GEM_RETRY_BASE": "0.01"}
    out = tmp_path / "live"
    p = run_cli(root, "--models", "anthropic", "gemini", "openai", "--out", str(out), "--workers", "6", env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert len(mock_server.state.requests) == 90
    r = pd.read_csv(out / "responses.csv", encoding="utf-8-sig")
    assert len(r) == 90 and set(r["status"]) == {"ok"}
    assert set(r["model_label"]) == {"anthropic:claude-opus-5-5", "gemini:gemini-flash-latest", "openai:gpt-5-mini"}
    assert not r["simulated"].any()
    s = pd.read_csv(out / "summary.csv", encoding="utf-8-sig").set_index("destination_id")
    # anthropic: toba x3 (danau toba, lake toba, samosir); openai: toba x1; gemini: 0 -> per 30 jawaban
    assert s.loc["danau_toba", "mentions"] == 30 * 3 + 30 * 1
    assert s.loc["bali", "mention_rate_pct"] == 100.0
    assert "SIMULASI" not in (out / "report.html").read_text(encoding="utf-8")


def test_analyze_only_matches(root, tmp_path):
    out = tmp_path / "a"
    assert run_cli(root, "--demo", "--out", str(out), "--max-questions", "4").returncode == 0
    out2 = tmp_path / "b"
    p = run_cli(root, "--analyze", str(out / "responses.csv"), "--out", str(out2))
    assert p.returncode == 0, p.stderr
    a = pd.read_csv(out / "summary.csv", encoding="utf-8-sig")
    b = pd.read_csv(out2 / "summary.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(a, b)


def test_resume(root, tmp_path, mock_server):
    env = {"ANTHROPIC_API_KEY": "k", "GEM_ANTHROPIC_BASE_URL": mock_server.base}
    out = tmp_path / "r"
    assert run_cli(root, "--models", "anthropic", "--max-questions", "2", "--out", str(out), env=env).returncode == 0
    lines = (out / "responses.jsonl").read_text(encoding="utf-8").splitlines()
    (out / "responses.jsonl").write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")  # simulasi putus
    n_before = len(mock_server.state.requests)
    p = run_cli(root, "--models", "anthropic", "--max-questions", "2", "--resume", str(out), env=env)
    assert p.returncode == 0 and "Melanjutkan: 2" in p.stdout
    assert len(mock_server.state.requests) - n_before == 2
    assert len(pd.read_csv(out / "responses.csv", encoding="utf-8-sig")) == 4


def test_missing_key_exit_code(root):
    p = run_cli(root, "--models", "anthropic")
    assert p.returncode == 2 and "ANTHROPIC_API_KEY" in p.stdout


def test_all_requests_failed_exit_code(root, tmp_path, mock_server):
    mock_server.state.unauthorized = True
    env = {"GEMINI_API_KEY": "bad", "GEM_GEMINI_BASE_URL": mock_server.base + "/v1beta"}
    p = run_cli(root, "--models", "gemini", "--max-questions", "1", "--out", str(tmp_path / "f"), env=env)
    assert p.returncode == 1 and "401" in p.stdout
    assert "Traceback" not in p.stderr, p.stderr
    assert (tmp_path / "f" / "report.html").is_file() and (tmp_path / "f" / "responses.csv").is_file()


def test_no_args_non_interactive_falls_back_to_demo(root, tmp_path):
    p = run_cli(root, "--out", str(tmp_path / "n"), "--max-questions", "1")
    assert p.returncode == 0 and "MODE DEMO" in p.stdout


def test_list_questions_and_help(root):
    p = run_cli(root, "--list-questions")
    assert p.returncode == 0 and len(p.stdout.strip().splitlines()) == 30
    assert run_cli(root, "--help").returncode == 0


def test_docs_config_in_sync(root, tmp_path):
    out = tmp_path / "c.json"
    assert run_cli(root, "--export-config", str(out)).returncode == 0
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(
        (root / "docs" / "data" / "config.json").read_text(encoding="utf-8")), \
        "jalankan: python gem_visibility_auditor.py --export-config docs/data/config.json"


def test_docs_demo_data_in_sync(root):
    """docs/data/demo_results.json harus sama dengan keluaran demo saat ini."""
    cfg = gva.load_config()
    recs = gva.run_audit([("demo", "simulasi-a"), ("demo", "simulasi-b")], cfg, ["id", "en"], workers=1)
    data = json.loads((root / "docs" / "data" / "demo_results.json").read_text(encoding="utf-8"))
    assert [r["response"] for r in recs] == [r["response"] for r in data["responses"]]
    assert data["config"] == cfg
