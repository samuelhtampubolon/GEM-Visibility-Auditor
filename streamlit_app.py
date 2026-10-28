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
    ANTHROPIC_API_KEY = "..."
    GEMINI_API_KEY = "..."
  Catatan keamanan: kunci di Secrets dipakai oleh SIAPA PUN yang membuka aplikasi. Untuk aplikasi publik,
  kosongkan Secrets dan biarkan tiap pengguna menempel kuncinya sendiri, atau batasi akses aplikasi.

Build .exe dashboard (opsional, bila suatu saat dibutuhkan):
  pip install pyinstaller streamlit pandas matplotlib requests
  pyinstaller --onefile --name GEM-Dashboard --collect-all streamlit --copy-metadata streamlit --add-data "streamlit_app.py:." --add-data "gem_visibility_auditor.py:." --hidden-import gem_visibility_auditor dashboard_launcher.py
  Hasil: dist/GEM-Dashboard.exe (membuka dashboard di browser, http://localhost:8501).
"""

from __future__ import annotations

import io
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
MAX_UPLOAD = 25 * 1024 * 1024
MODES = ["Jalankan audit baru", "Unggah hasil", "Contoh (demo)"]
HIGHLIGHT_CSS = ("<style>mark.focus{background:#cde2fb;color:#0b0b0b}mark.competitor{background:#fbd9c9;"
                 "color:#0b0b0b}mark.other{background:#e1e0d9;color:#0b0b0b}.gem-answer{white-space:pre-wrap;"
                 "font-size:14px}</style>")


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
    """Baca unggahan di memori (tanpa file sementara) dengan batas ukuran dan validasi kolom."""
    raw = file.getvalue()
    if len(raw) > MAX_UPLOAD:
        raise ValueError("file lebih dari 25 MB")
    if file.name.lower().endswith(".json"):
        data = json.loads(raw.decode("utf-8-sig"))
        records = data.get("responses") if isinstance(data, dict) else data
        if not isinstance(records, list) or not records or not all(isinstance(r, dict) for r in records):
            raise ValueError("JSON tidak berisi daftar 'responses'")
        df = gva.records_to_df(records)
    else:
        df = gva.read_responses_csv(io.BytesIO(raw))
    if not len(df) or (df["model_label"].astype(str) == "").all():
        raise ValueError("kolom 'response' dan 'model' wajib ada")
    return df


def run_with_progress(models, langs, runs, max_q, keys, opts) -> list:
    """Audit berjalan di thread latar; progress bar diperbarui dari thread utama."""
    state = {"done": 0, "ok": 0, "total": len(gva.build_tasks(models, CFG, langs, runs, max_q)), "last": ""}
    box: dict = {}

    def progress(done, total, rec):
        state["done"], state["total"] = done, total
        state["ok"] += rec["status"] == "ok"
        state["last"] = f"{rec['model_label']} {rec['question_id']}-{rec['language']}: {rec['status']}"

    def worker():
        try:
            box["records"] = gva.run_audit(models, CFG, langs, runs, max_q, keys, opts, workers=4, progress=progress)
        except Exception as exc:  # tampilkan di UI
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    with st.status("Audit berjalan...", expanded=True) as status:
        bar = st.progress(0.0, text="Menyiapkan...")
        while t.is_alive():
            frac = state["done"] / state["total"] if state["total"] else 0
            bar.progress(min(frac, 1.0), text=f"{state['done']}/{state['total']} selesai, {state['ok']} berhasil  |  {state['last']}")
            time.sleep(0.3)
        t.join()
        bar.progress(1.0, text=f"{state['done']}/{state['total']} selesai, {state['ok']} berhasil")
        status.update(label=f"Audit selesai: {state['ok']} berhasil, {state['done'] - state['ok']} gagal",
                      state="complete" if state["ok"] else "error", expanded=False)
    if "error" in box:
        raise box["error"]
    return box["records"]


def set_results(df: pd.DataFrame, source: str) -> None:
    st.session_state["df"] = df
    st.session_state["source"] = source
    st.session_state.pop("zip_bytes", None)


def answer_html(text: str, matchers: list, cfg: dict) -> str:
    # Semua teks di-escape oleh _highlight_html; hanya tag <mark> buatan sendiri yang tersisa.
    return f"<div class='gem-answer'>{gva._highlight_html(text, matchers, cfg)}</div>"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("GEM Visibility Auditor")
st.sidebar.caption(f"v{gva.__version__} | share of AI voice destinasi wisata")
mode = st.sidebar.radio("Sumber data", MODES, key="mode", horizontal=False)

if mode == "Contoh (demo)":
    if st.session_state.get("source") != "demo":
        set_results(gva.records_to_df(demo_records()), "demo")

elif mode == "Jalankan audit baru":
    choices = [p for p in gva.PROVIDERS]
    default = [p for p in gva.PROVIDERS if gva.PROVIDERS[p]["env"] and secret_key(p)] or ["demo"]
    providers = st.sidebar.multiselect("Model AI", choices, default=default,
                                       format_func=lambda p: gva.PROVIDERS[p]["label"], key="providers")
    models, keys = [], {}
    for p in providers:
        info = gva.PROVIDERS[p]
        with st.sidebar.expander(info["label"], expanded=not info.get("no_key")):
            m = st.text_input("Model (pisahkan koma untuk beberapa)", info["default_model"], key=f"model_{p}")
            if not info.get("no_key"):
                found = secret_key(p)
                k = st.text_input(f"Kunci API ({info['env'][0]})", type="password", key=f"key_{p}",
                                  placeholder="terdeteksi dari secrets/env" if found else "tempel kunci di sini",
                                  help="Hanya disimpan di sesi ini, tidak ditulis ke file atau log.")
                keys[p] = k.strip() or found
            if p == "ollama":
                st.caption("Ollama harus berjalan di komputer yang sama (http://localhost:11434).")
        for one in [x.strip() for x in m.split(",") if x.strip()]:
            models.append((p, one))
    langs = st.sidebar.multiselect("Bahasa", ["id", "en"], default=["id", "en"],
                                   format_func=lambda x: gva.LANG_LABELS[x], key="langs")
    runs = st.sidebar.number_input("Pengulangan per pertanyaan", 1, 10, 1, key="runs")
    max_q = st.sidebar.slider("Jumlah topik", 1, len(CFG["questions"]), len(CFG["questions"]), key="max_q")
    effort = st.sidebar.selectbox("Effort Claude", ["low", "medium", "high"], key="effort",
                                  help="low = hemat biaya; naikkan bila butuh jawaban lebih dalam")
    n_req = len(gva.build_tasks(models, CFG, langs, int(runs), int(max_q)))
    st.sidebar.info(f"**{n_req} permintaan** ke {len(models)} model")
    missing = [p for p, _ in models if not gva.PROVIDERS[p].get("no_key") and not keys.get(p)]
    if missing:
        st.sidebar.warning("Kunci API belum ada untuk: " + ", ".join(sorted(set(missing))))
    run_clicked = st.sidebar.button("Jalankan audit", type="primary", disabled=not models or not langs or bool(missing),
                                    key="run_btn", width="stretch")
    if st.sidebar.button("Hapus kunci dari sesi", key="clear_keys", width="stretch"):
        for k in [k for k in st.session_state if str(k).startswith("key_")]:
            del st.session_state[k]
        st.rerun()
    if run_clicked:
        opts = {"claude_effort": effort, "timeout": 180}
        records = run_with_progress(models, langs, int(runs), int(max_q), keys, opts)
        keys.clear()
        set_results(gva.records_to_df(records), "run")

else:
    up = st.sidebar.file_uploader("responses.csv atau dashboard_data.json", type=["csv", "json"], key="upload",
                                  help="Diproses di memori server sesi ini, tidak disimpan.")
    if up is not None and st.session_state.get("source") != f"upload:{up.name}:{up.size}":
        try:
            set_results(load_uploaded(up), f"upload:{up.name}:{up.size}")
        except Exception as exc:
            st.sidebar.error(f"File tidak bisa dibaca: {exc}")

df = st.session_state.get("df")
if df is not None and len(df):
    st.sidebar.divider()
    st.sidebar.subheader("Fokus analisis")
    names = {d["id"]: d["name"] for d in CFG["destinations"]}
    focus = st.sidebar.selectbox("Destinasi fokus", list(names), index=list(names).index(CFG["focus"]),
                                 format_func=names.get, key="focus")
    comp_default = [c for c in CFG["competitors"] if c != focus]
    competitors = st.sidebar.multiselect("Pembanding (maks. 3)", [d for d in names if d != focus],
                                         default=comp_default, format_func=names.get, max_selections=3,
                                         key=f"comps_{focus}")
    view_cfg = dict(CFG, focus=focus, competitors=competitors)
else:
    view_cfg = CFG

# ---------------------------------------------------------------------------
# Tampilan hasil
# ---------------------------------------------------------------------------
if df is None or len(df) == 0:
    st.title("Seberapa sering AI merekomendasikan Danau Toba?")
    st.markdown("Kirim **30 pertanyaan wisata** (15 topik, Bahasa Indonesia dan Inggris) ke Claude, Gemini, "
                "ChatGPT, dan lainnya, lalu ukur **share of AI voice** Danau Toba dibanding Bali, Labuan Bajo, "
                "dan 8 destinasi lain.")
    c1, c2, c3 = st.columns(3)
    c1.info("**1. Jalankan audit**  \nPilih model di sidebar, tempel kunci API, klik Jalankan audit.")
    c2.info("**2. Unggah hasil**  \nBuka responses.csv atau dashboard_data.json dari CLI, .exe, atau Colab.")
    c3.info("**3. Contoh (demo)**  \nCoba semua fitur dengan data simulasi tanpa kunci API.")
    st.stop()

res = gva.analyze(df, view_cfg)
h = res["headline"]
st.title(f"Share of AI voice: {h['focus_name']}")
if h["simulated"]:
    st.warning("Data ini SIMULASI (mode demo), bukan jawaban LLM sungguhan.")
if h["responses_error"]:
    st.error(f"{h['responses_error']} dari {h['responses_total']} permintaan gagal. Lihat tab Jawaban (status error).")
st.caption(f"{h['responses_ok']} jawaban berhasil dari {len(h['models'])} model: {', '.join(h['models'])}")

cols = st.columns(2 + len(h["competitors"]))
cols[0].metric(f"SOV {h['focus_name']}", f"{h['focus_sov_pct']:.1f}%", border=True,
               help="Share of AI voice: sebutan destinasi / total sebutan semua destinasi")
cols[1].metric(f"Peringkat {h['focus_name']}", f"{h['focus_rank']} / {h['destinations']}", border=True,
               help=f"Disebut di {h['focus_mention_rate_pct']:.1f}% jawaban")
for i, c in enumerate(h["competitors"], 2):
    ratio = f"{c['focus_per_100']:.0f}" if c["focus_per_100"] is not None else "-"
    cols[i].metric(f"SOV {c['name']}", f"{c['sov_pct']:.1f}%", border=True,
                   help=f"Setiap 100 sebutan {c['name']}, {h['focus_name']} disebut {ratio} kali")

insights = gva.build_insights(res)
if insights:
    with st.container(border=True):
        st.markdown("**Insight**")
        for t in insights:
            st.markdown(f"- {t}")

tabs = st.tabs(["Share of voice", "Per bahasa", "Per model", "Per kategori", "Jawaban", "Unduh"])
with tabs[0]:
    c1, c2 = st.columns(2)
    c1.pyplot(gva.fig_share_of_voice(res), clear_figure=True)
    c2.pyplot(gva.fig_mention_rate(res), clear_figure=True)
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
        piv = bc.pivot_table(index="category", columns="destination", values="share_of_voice_pct", aggfunc="first")
        order = [h["focus_name"]] + [c["name"] for c in h["competitors"]]
        order += [d for d in res["summary"]["destination"] if d not in order]
        st.caption("Share of AI voice (%) per kategori pertanyaan; kolom pertama = fokus, lalu pembanding")
        st.dataframe(piv.reindex(columns=order).style.format("{:.1f}").background_gradient(cmap="Blues", axis=None),
                     width="stretch")
with tabs[4]:
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    q = c1.text_input("Cari", placeholder="cari di pertanyaan atau jawaban", key="f_search")
    f_model = c2.selectbox("Model", ["(semua)"] + sorted(df["model_label"].unique()), key="f_model")
    f_lang = c3.selectbox("Bahasa", ["(semua)"] + sorted(df["language"].unique()), key="f_lang")
    f_status = c4.selectbox("Status", ["(semua)", "ok", "error"], key="f_status")
    view = df
    if f_model != "(semua)":
        view = view[view["model_label"] == f_model]
    if f_lang != "(semua)":
        view = view[view["language"] == f_lang]
    if f_status != "(semua)":
        view = view[view["status"] == f_status]
    if q:
        mask = (view["prompt"].astype(str) + "\n" + view["response"].astype(str)).str.contains(q, case=False, regex=False)
        view = view[mask]
    matchers = gva.build_matchers(view_cfg["destinations"])
    st.caption(f"{len(view)} jawaban (maks. 50 ditampilkan). Sorotan biru = fokus, oranye = pembanding.")
    for r in view.head(50).to_dict("records"):
        with st.expander(f"{r['model_label']} | {r['question_id']}-{r['language']} | {r['prompt']}"):
            if r["status"] != "ok":
                st.error(r["error"])
            else:
                # st.html menyanitasi HTML (DOMPurify) dan mengabaikan JavaScript; teks juga sudah di-escape.
                st.html(HIGHLIGHT_CSS + answer_html(r["response"], matchers, view_cfg))
with tabs[5]:
    st.caption("CSV aman dibuka di Excel/Sheets (sel yang diawali formula dinetralkan).")
    c1, c2, c3 = st.columns(3)
    c1.download_button("responses.csv", gva.to_csv_bytes(df), "responses.csv", "text/csv", width="stretch")
    c2.download_button("summary.csv", gva.to_csv_bytes(res["summary"]), "summary.csv", "text/csv", width="stretch")
    c3.download_button("mentions.csv", gva.to_csv_bytes(res["mentions"]), "mentions.csv", "text/csv", width="stretch")
    if st.button("Siapkan paket lengkap (.zip: CSV, PNG, report.html)", key="zip_btn"):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gem_audit"
            gva.export_outputs(df, res, view_cfg, out)
            st.session_state["zip_bytes"] = gva.zip_outputs(out).read_bytes()
    if st.session_state.get("zip_bytes"):
        st.download_button("Unduh gem_audit.zip", st.session_state["zip_bytes"], "gem_audit.zip", "application/zip")

st.sidebar.caption("Kunci API tidak pernah ditulis ke file, log, atau ekspor.")
