#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEM Visibility Auditor: dashboard Streamlit.

Jalankan lokal:
  pip install -r requirements.txt
  streamlit run streamlit_app.py

Deploy (Streamlit Community Cloud):
  share.streamlit.io > New app > pilih repo ini, branch, file utama streamlit_app.py.
  Kunci API (opsional) diisi di Settings > Secrets, contoh:
    ANTHROPIC_API_KEY = "sk-ant-..."
    GEMINI_API_KEY = "..."
    OPENAI_API_KEY = "sk-..."

Build .exe dashboard (opsional, bila suatu saat dibutuhkan):
  pip install pyinstaller streamlit pandas matplotlib requests
  pyinstaller --onefile --name GEM-Dashboard --collect-all streamlit --copy-metadata streamlit --add-data "streamlit_app.py:." --add-data "gem_visibility_auditor.py:." --hidden-import gem_visibility_auditor dashboard_launcher.py
  Hasil: dist/GEM-Dashboard.exe (membuka dashboard di browser, http://localhost:8501).
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gem_visibility_auditor as gva  # noqa: E402

st.set_page_config(page_title="GEM Visibility Auditor", page_icon="📊", layout="wide")

CFG = gva.load_config()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def secret_key(provider: str) -> str | None:
    for name in gva.PROVIDERS[provider]["env"]:
        try:
            val = st.secrets.get(name)  # type: ignore[attr-defined]
        except Exception:
            val = None
        if val:
            return str(val)
    return gva.resolve_key(provider)


@st.cache_data(show_spinner=False)
def demo_records() -> list:
    models = [("demo", "simulasi-a"), ("demo", "simulasi-b")]
    return gva.run_audit(models, CFG, ["id", "en"], runs=1, workers=1)


def load_uploaded(file) -> pd.DataFrame:
    name = file.name.lower()
    raw = file.getvalue()
    if name.endswith(".json"):
        data = json.loads(raw.decode("utf-8-sig"))
        records = data.get("responses", data) if isinstance(data, dict) else data
        return gva.records_to_df(records)
    tmp = Path(tempfile.mkdtemp()) / "responses.csv"
    tmp.write_bytes(raw)
    return gva.read_responses_csv(str(tmp))


def run_with_progress(models, langs, runs, max_q, keys, opts) -> list:
    """Audit berjalan di thread latar; progress bar diperbarui dari thread utama."""
    state = {"done": 0, "total": len(gva.build_tasks(models, CFG, langs, runs, max_q)), "last": ""}
    box: dict = {}

    def progress(done, total, rec):
        state["done"], state["total"] = done, total
        state["last"] = f"{rec['model_label']} {rec['question_id']}-{rec['language']}: {rec['status']}"

    def worker():
        try:
            box["records"] = gva.run_audit(models, CFG, langs, runs, max_q, keys, opts, workers=4, progress=progress)
        except Exception as exc:  # tampilkan di UI
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    bar = st.progress(0.0, text="Menyiapkan...")
    while t.is_alive():
        frac = state["done"] / state["total"] if state["total"] else 0
        bar.progress(min(frac, 1.0), text=f"{state['done']}/{state['total']}  {state['last']}")
        time.sleep(0.3)
    t.join()
    bar.progress(1.0, text=f"Selesai: {state['done']}/{state['total']} permintaan")
    if "error" in box:
        raise box["error"]
    return box["records"]


def set_results(df: pd.DataFrame, source: str) -> None:
    st.session_state["df"] = df
    st.session_state["source"] = source


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("GEM Visibility Auditor")
st.sidebar.caption(f"v{gva.__version__} | share of AI voice destinasi wisata")
mode = st.sidebar.radio("Sumber data", ["Contoh (demo)", "Jalankan audit baru", "Unggah hasil"], key="mode")

if mode == "Contoh (demo)":
    if st.session_state.get("source") != "demo":
        set_results(gva.records_to_df(demo_records()), "demo")

elif mode == "Jalankan audit baru":
    choices = [p for p in gva.PROVIDERS]
    default = [p for p in gva.PROVIDERS if gva.PROVIDERS[p]["env"] and secret_key(p)] or ["demo"]
    providers = st.sidebar.multiselect("Provider", choices, default=default,
                                       format_func=lambda p: gva.PROVIDERS[p]["label"], key="providers")
    models, keys = [], {}
    for p in providers:
        info = gva.PROVIDERS[p]
        with st.sidebar.expander(info["label"], expanded=False):
            m = st.text_input("Model (pisahkan koma untuk beberapa)", info["default_model"], key=f"model_{p}")
            if not info.get("no_key"):
                found = secret_key(p)
                k = st.text_input(f"Kunci API ({info['env'][0]})", type="password", key=f"key_{p}",
                                  placeholder="terdeteksi dari secrets/env" if found else "tempel kunci di sini")
                keys[p] = k.strip() or found
            if p == "ollama":
                st.caption("Ollama harus berjalan di komputer ini (http://localhost:11434).")
        for one in [x.strip() for x in m.split(",") if x.strip()]:
            models.append((p, one))
    langs = st.sidebar.multiselect("Bahasa", ["id", "en"], default=["id", "en"],
                                   format_func=lambda x: gva.LANG_LABELS[x], key="langs")
    runs = st.sidebar.number_input("Pengulangan per pertanyaan", 1, 10, 1, key="runs")
    max_q = st.sidebar.slider("Jumlah topik", 1, len(CFG["questions"]), len(CFG["questions"]), key="max_q")
    effort = st.sidebar.selectbox("Effort Claude", ["low", "medium", "high"], key="effort")
    n_req = len(gva.build_tasks(models, CFG, langs, int(runs), int(max_q)))
    st.sidebar.caption(f"Total permintaan: {n_req}")
    missing = [p for p, _ in models if not gva.PROVIDERS[p].get("no_key") and not keys.get(p)]
    if missing:
        st.sidebar.warning("Kunci API belum ada untuk: " + ", ".join(sorted(set(missing))))
    if st.sidebar.button("Jalankan audit", type="primary", disabled=not models or not langs or bool(missing),
                         key="run_btn"):
        opts = {"claude_effort": effort, "timeout": 180}
        records = run_with_progress(models, langs, int(runs), int(max_q), keys, opts)
        set_results(gva.records_to_df(records), "run")

else:
    up = st.sidebar.file_uploader("responses.csv atau dashboard_data.json", type=["csv", "json"], key="upload")
    if up is not None and st.session_state.get("source") != f"upload:{up.name}:{up.size}":
        try:
            set_results(load_uploaded(up), f"upload:{up.name}:{up.size}")
        except Exception as exc:
            st.sidebar.error(f"File tidak bisa dibaca: {exc}")

# ---------------------------------------------------------------------------
# Tampilan hasil
# ---------------------------------------------------------------------------
st.title("Share of AI voice: destinasi wisata Indonesia")
df = st.session_state.get("df")
if df is None or len(df) == 0:
    st.info("Pilih sumber data di sidebar: contoh demo, jalankan audit baru, atau unggah hasil.")
    st.stop()

res = gva.analyze(df, CFG)
h = res["headline"]
if h["simulated"]:
    st.warning("Data ini SIMULASI (mode demo), bukan jawaban LLM sungguhan. "
               "Pilih 'Jalankan audit baru' dengan kunci API untuk audit nyata.")
if h["responses_error"]:
    st.error(f"{h['responses_error']} permintaan gagal. Lihat tab Jawaban untuk detail error.")
st.caption(f"{h['responses_ok']} jawaban berhasil dari {len(h['models'])} model: {', '.join(h['models'])}")

cols = st.columns(1 + len(h["competitors"]) + 1)
cols[0].metric(f"SOV {h['focus_name']}", f"{h['focus_sov_pct']:.1f}%",
               help="Share of AI voice: sebutan destinasi / total sebutan semua destinasi")
for i, c in enumerate(h["competitors"], 1):
    ratio = f"{c['focus_per_100']:.0f}" if c["focus_per_100"] is not None else "-"
    cols[i].metric(f"SOV {c['name']}", f"{c['sov_pct']:.1f}%",
                   help=f"Setiap 100 sebutan {c['name']}, {h['focus_name']} disebut {ratio} kali")
cols[-1].metric(f"Peringkat {h['focus_name']}", f"{h['focus_rank']} / {h['destinations']}",
                help=f"Disebut di {h['focus_mention_rate_pct']:.1f}% jawaban")
st.markdown(gva.headline_text(h).replace("\n", "  \n"))

tabs = st.tabs(["Share of voice", "Per bahasa", "Per model", "Per kategori", "Jawaban", "Unduh"])
with tabs[0]:
    st.pyplot(gva.fig_share_of_voice(res), clear_figure=True)
    st.pyplot(gva.fig_mention_rate(res), clear_figure=True)
    st.dataframe(res["summary"], hide_index=True, width="stretch")
with tabs[1]:
    st.pyplot(gva.fig_by_language(res), clear_figure=True)
    piv = res["by_language"].pivot_table(index="destination", columns="language",
                                         values="share_of_voice_pct", aggfunc="first")
    st.dataframe(piv.reindex(res["summary"]["destination"]), width="stretch")
with tabs[2]:
    st.pyplot(gva.fig_by_model(res), clear_figure=True)
    st.dataframe(res["by_model"], hide_index=True, width="stretch")
with tabs[3]:
    bc = res["by_category"]
    if len(bc):
        piv = bc.pivot_table(index="destination", columns="category", values="share_of_voice_pct", aggfunc="first")
        st.caption("Share of AI voice (%) per kategori pertanyaan")
        st.dataframe(piv.reindex(res["summary"]["destination"]).style.format("{:.1f}")
                     .background_gradient(cmap="Blues", axis=None), width="stretch")
with tabs[4]:
    c1, c2, c3 = st.columns(3)
    f_model = c1.selectbox("Model", ["(semua)"] + sorted(df["model_label"].unique()), key="f_model")
    f_lang = c2.selectbox("Bahasa", ["(semua)"] + sorted(df["language"].unique()), key="f_lang")
    f_status = c3.selectbox("Status", ["(semua)", "ok", "error"], key="f_status")
    view = df
    if f_model != "(semua)":
        view = view[view["model_label"] == f_model]
    if f_lang != "(semua)":
        view = view[view["language"] == f_lang]
    if f_status != "(semua)":
        view = view[view["status"] == f_status]
    matchers = gva.build_matchers(CFG["destinations"])
    st.caption(f"{len(view)} jawaban (maks. 50 ditampilkan). Sorotan biru = fokus, oranye = kompetitor.")
    for r in view.head(50).to_dict("records"):
        with st.expander(f"{r['model_label']} | {r['question_id']}-{r['language']} | {r['prompt']}"):
            if r["status"] != "ok":
                st.error(r["error"])
            else:
                body = gva._highlight_html(r["response"], matchers, CFG)
                st.markdown(
                    "<style>mark.focus{background:#cde2fb;color:#0b0b0b}mark.competitor{background:#fbd9c9;"
                    "color:#0b0b0b}mark.other{background:#e1e0d9;color:#0b0b0b}</style>"
                    f"<div style='white-space:pre-wrap;font-size:14px'>{body}</div>", unsafe_allow_html=True)
with tabs[5]:
    st.download_button("responses.csv", df.to_csv(index=False).encode("utf-8-sig"), "responses.csv", "text/csv")
    st.download_button("summary.csv", res["summary"].to_csv(index=False).encode("utf-8-sig"), "summary.csv", "text/csv")
    st.download_button("mentions.csv", res["mentions"].to_csv(index=False).encode("utf-8-sig"), "mentions.csv", "text/csv")
    if st.button("Siapkan paket lengkap (.zip: CSV, PNG, report.html)", key="zip_btn"):
        out = Path(tempfile.mkdtemp()) / "gem_audit"
        gva.export_outputs(df, res, CFG, out)
        zpath = gva.zip_outputs(out)
        st.session_state["zip_bytes"] = zpath.read_bytes()
    if st.session_state.get("zip_bytes"):
        st.download_button("Unduh gem_audit.zip", st.session_state["zip_bytes"], "gem_audit.zip", "application/zip")
