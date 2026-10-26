#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEM Visibility Auditor v1.0.0
Pilar GEM (Generative Engine Marketing), marketing intelligence pariwisata Indonesia.

Skrip ini menembakkan 30 pertanyaan wisata (15 topik x Bahasa Indonesia + Inggris)
ke API LLM (Claude, Gemini, OpenAI, Groq, DeepSeek, OpenRouter, Mistral, Ollama),
lalu menghitung berapa kali Danau Toba disebut dibanding Bali, Labuan Bajo, dan
destinasi lain. Output: CSV, grafik "share of AI voice" (Pandas + Matplotlib),
laporan HTML, dan dashboard_data.json untuk dashboard web.

------------------------------------------------------------------------------
CARA PAKAI 1: GOOGLE COLAB (copy-paste satu sel)
  1. Buka https://colab.research.google.com, buat notebook baru.
  2. (Opsional) Simpan kunci API di Colab Secrets (ikon kunci di panel kiri),
     nama: ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, dst. Aktifkan
     "Notebook access". Tanpa kunci, Anda akan ditanya, atau mode demo berjalan.
  3. Salin SELURUH isi file ini ke SATU sel, lalu jalankan (Shift+Enter).
     Pengaturan Colab ada di variabel NOTEBOOK_SETTINGS di bawah.
  Pandas, Matplotlib, dan Requests sudah terpasang di Colab.

CARA PAKAI 2: LOKAL (Python 3.9+)
  pip install -r requirements.txt          (atau: pip install pandas matplotlib requests)
  python gem_visibility_auditor.py --demo                 # uji tanpa kunci API (simulasi)
  python gem_visibility_auditor.py                        # wizard interaktif
  python gem_visibility_auditor.py --models anthropic gemini openai --runs 2
  python gem_visibility_auditor.py --models anthropic:claude-opus-5-5 gemini:gemini-flash-latest
  python gem_visibility_auditor.py --analyze gem_audit_output/audit_X/responses.csv

  Kunci API dibaca dari environment variable atau file .env di folder kerja:
    ANTHROPIC_API_KEY, GEMINI_API_KEY (atau GOOGLE_API_KEY), OPENAI_API_KEY,
    GROQ_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY.

CARA PAKAI 3: BUILD .EXE (Windows/macOS/Linux)
  pip install pyinstaller pandas matplotlib requests
  pyinstaller --onefile --name GEM-Visibility-Auditor gem_visibility_auditor.py
  Hasil: dist/GEM-Visibility-Auditor.exe (klik dua kali = wizard interaktif,
  atau jalankan dari terminal dengan argumen yang sama seperti di atas).

CARA PAKAI 4: DASHBOARD
  streamlit run streamlit_app.py           (dashboard interaktif, bisa dideploy
                                            ke Streamlit Community Cloud)
  Dashboard web statis (GitHub Pages) ada di folder docs/.
------------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import datetime as _dt
import hashlib
import html
import json
import os
import random
import re
import sys
import threading
import time
import unicodedata
import webbrowser
import zipfile
from pathlib import Path

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Pengaturan khusus Google Colab / Jupyter (dipakai saat file ditempel ke sel).
# ---------------------------------------------------------------------------
NOTEBOOK_SETTINGS = {
    # Daftar model "provider" atau "provider:model". Kosong = otomatis
    # (semua provider yang kuncinya ditemukan; jika tidak ada, tanya / demo).
    "models": [],
    "languages": ["id", "en"],
    "runs": 1,                 # pengulangan per pertanyaan (LLM tidak deterministik)
    "max_questions": 0,        # 0 = semua 15 topik (30 pertanyaan per model)
    "ask_for_keys": True,      # tanya kunci API lewat getpass bila tidak ditemukan
    "download_zip": True,      # di Colab: unduh hasil sebagai .zip
    "output_dir": "gem_audit_output",
}

# ---------------------------------------------------------------------------
# Provider & model bawaan
# ---------------------------------------------------------------------------
ANTHROPIC_VERSION = "2026-10-21"
CLAUDE_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

PROVIDERS = {
    "anthropic": {
        "label": "Claude (Anthropic)",
        "kind": "anthropic",
        "default_model": "claude-opus-5-5",
        "env": ["ANTHROPIC_API_KEY"],
        "base_url": "https://api.anthropic.com",
        "base_env": "GEM_ANTHROPIC_BASE_URL",
    },
    "gemini": {
        "label": "Gemini (Google)",
        "kind": "gemini",
        "default_model": "gemini-flash-latest",
        "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "base_env": "GEM_GEMINI_BASE_URL",
    },
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "kind": "openai",
        "default_model": "gpt-5-mini",
        "env": ["OPENAI_API_KEY"],
        "base_url": "https://api.openai.com/v1",
        "base_env": "GEM_OPENAI_BASE_URL",
    },
    "groq": {
        "label": "Groq",
        "kind": "openai_compat",
        "default_model": "llama-3.3-70b-versatile",
        "env": ["GROQ_API_KEY"],
        "base_url": "https://api.groq.com/openai/v1",
        "base_env": "GEM_GROQ_BASE_URL",
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "openai_compat",
        "default_model": "deepseek-chat",
        "env": ["DEEPSEEK_API_KEY"],
        "base_url": "https://api.deepseek.com/v1",
        "base_env": "GEM_DEEPSEEK_BASE_URL",
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "openai_compat",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "env": ["OPENROUTER_API_KEY"],
        "base_url": "https://openrouter.ai/api/v1",
        "base_env": "GEM_OPENROUTER_BASE_URL",
    },
    "mistral": {
        "label": "Mistral",
        "kind": "openai_compat",
        "default_model": "mistral-small-latest",
        "env": ["MISTRAL_API_KEY"],
        "base_url": "https://api.mistral.ai/v1",
        "base_env": "GEM_MISTRAL_BASE_URL",
    },
    "ollama": {
        "label": "Ollama (lokal)",
        "kind": "openai_compat",
        "default_model": "llama3.1",
        "env": [],
        "no_key": True,
        "base_url": "http://localhost:11434/v1",
        "base_env": "GEM_OLLAMA_BASE_URL",
    },
    "demo": {
        "label": "Demo (simulasi offline, bukan data nyata)",
        "kind": "demo",
        "default_model": "simulasi-a",
        "env": [],
        "no_key": True,
        "base_url": "",
        "base_env": "",
    },
}

# ---------------------------------------------------------------------------
# Destinasi & pertanyaan (bisa diganti lewat --config file.json)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "focus": "danau_toba",
    "competitors": ["bali", "labuan_bajo"],
    "destinations": [
        {"id": "danau_toba", "name": "Danau Toba",
         "aliases": ["danau toba", "lake toba", "toba", "samosir", "parapat", "balige"]},
        {"id": "bali", "name": "Bali",
         "aliases": ["bali", "balinese", "ubud", "seminyak", "canggu", "nusa dua", "nusa penida",
                     "uluwatu", "kintamani", "sanur", "jimbaran"]},
        {"id": "labuan_bajo", "name": "Labuan Bajo",
         "aliases": ["labuan bajo", "komodo", "pulau padar", "padar island"]},
        {"id": "raja_ampat", "name": "Raja Ampat",
         "aliases": ["raja ampat", "waisai", "wayag", "piaynemo"]},
        {"id": "yogyakarta", "name": "Yogyakarta & Borobudur",
         "aliases": ["yogyakarta", "jogjakarta", "jogja", "yogya", "borobudur", "prambanan"]},
        {"id": "lombok", "name": "Lombok & Mandalika",
         "aliases": ["lombok", "mandalika", "gili trawangan", "gili air", "gili meno",
                     "gili islands", "kepulauan gili", "rinjani"]},
        {"id": "bromo", "name": "Bromo Tengger Semeru",
         "aliases": ["bromo", "tengger", "semeru"]},
        {"id": "likupang", "name": "Likupang & Bunaken",
         "aliases": ["likupang", "bunaken", "manado"]},
        {"id": "wakatobi", "name": "Wakatobi", "aliases": ["wakatobi"]},
        {"id": "belitung", "name": "Belitung", "aliases": ["belitung"]},
        {"id": "kelimutu", "name": "Kelimutu", "aliases": ["kelimutu"]},
    ],
    "questions": [
        {"qid": "Q01", "category": "Umum",
         "text": {"id": "Apa saja 5 destinasi wisata terbaik di Indonesia yang wajib dikunjungi?",
                  "en": "What are the top 5 must-visit travel destinations in Indonesia?"}},
        {"qid": "Q02", "category": "Itinerary",
         "text": {"id": "Saya punya waktu 7 hari untuk liburan di Indonesia. Destinasi mana yang sebaiknya saya kunjungi?",
                  "en": "I have 7 days for a holiday in Indonesia. Which destinations should I visit?"}},
        {"qid": "Q03", "category": "Bulan madu",
         "text": {"id": "Rekomendasikan destinasi bulan madu paling romantis di Indonesia.",
                  "en": "Recommend the most romantic honeymoon destinations in Indonesia."}},
        {"qid": "Q04", "category": "Keluarga",
         "text": {"id": "Destinasi wisata di Indonesia apa yang cocok untuk liburan keluarga dengan anak-anak?",
                  "en": "Which Indonesian destinations are best for a family holiday with kids?"}},
        {"qid": "Q05", "category": "Hemat",
         "text": {"id": "Di mana tempat liburan yang murah tapi indah di Indonesia untuk backpacker?",
                  "en": "Where can backpackers find affordable yet beautiful places to travel in Indonesia?"}},
        {"qid": "Q06", "category": "Alam",
         "text": {"id": "Destinasi wisata alam dengan pemandangan paling spektakuler di Indonesia apa saja?",
                  "en": "Which nature destinations in Indonesia have the most spectacular scenery?"}},
        {"qid": "Q07", "category": "Budaya",
         "text": {"id": "Di mana saya bisa merasakan budaya dan tradisi lokal yang autentik di Indonesia?",
                  "en": "Where can I experience authentic local culture and traditions in Indonesia?"}},
        {"qid": "Q08", "category": "Danau",
         "text": {"id": "Danau terindah di Indonesia yang layak dikunjungi apa saja?",
                  "en": "What are the most beautiful lakes to visit in Indonesia?"}},
        {"qid": "Q09", "category": "Hidden gem",
         "text": {"id": "Destinasi tersembunyi (hidden gem) di Indonesia yang belum terlalu ramai turis apa saja?",
                  "en": "What are some hidden-gem destinations in Indonesia that are not yet crowded with tourists?"}},
        {"qid": "Q10", "category": "Bahari",
         "text": {"id": "Di mana tempat terbaik untuk menyelam dan snorkeling di Indonesia?",
                  "en": "Where are the best places for diving and snorkeling in Indonesia?"}},
        {"qid": "Q11", "category": "Petualangan",
         "text": {"id": "Destinasi petualangan terbaik di Indonesia untuk mendaki gunung atau trekking apa saja?",
                  "en": "What are the best adventure destinations in Indonesia for hiking or trekking?"}},
        {"qid": "Q12", "category": "Ekowisata",
         "text": {"id": "Rekomendasikan destinasi ekowisata dan wisata berkelanjutan di Indonesia.",
                  "en": "Recommend eco-tourism and sustainable travel destinations in Indonesia."}},
        {"qid": "Q13", "category": "Kuliner",
         "text": {"id": "Destinasi wisata kuliner terbaik di Indonesia di mana saja?",
                  "en": "Which Indonesian destinations are best for food and culinary travel?"}},
        {"qid": "Q14", "category": "Tinggal lama",
         "text": {"id": "Di mana tempat terbaik di Indonesia untuk tinggal lama atau bekerja jarak jauh sebagai digital nomad?",
                  "en": "Where are the best places in Indonesia for a long stay or for digital nomads?"}},
        {"qid": "Q15", "category": "Tren",
         "text": {"id": "Destinasi wisata Indonesia apa yang sedang naik daun dan layak dikunjungi tahun ini?",
                  "en": "Which Indonesian travel destinations are trending and worth visiting this year?"}},
    ],
}

LANG_LABELS = {"id": "Bahasa Indonesia", "en": "English"}
GROUP_LABELS = {"focus": "Fokus", "competitor": "Kompetitor utama", "other": "Destinasi lain"}

RESPONSE_COLUMNS = [
    "response_id", "timestamp", "provider", "model", "model_label", "question_id", "category",
    "language", "run", "prompt", "response", "status", "error", "latency_s",
    "input_tokens", "output_tokens", "stop_reason", "simulated",
]

# Warna (palet tervalidasi; teks memakai token tinta, bukan warna seri).
COLORS = {
    "focus": "#2a78d6", "competitor": "#eb6834", "other": "#c3c2b7",
    "lang_id": "#2a78d6", "lang_en": "#eb6834",
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb",
}

_print_lock = threading.Lock()


def log(msg: str = "") -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
def load_config(path: str | None = None) -> dict:
    """Muat konfigurasi bawaan, lalu timpa dengan file JSON (jika ada)."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        for key in ("focus", "competitors", "destinations", "questions"):
            if key in user:
                cfg[key] = user[key]
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict) -> None:
    ids = [d["id"] for d in cfg["destinations"]]
    if len(ids) != len(set(ids)):
        raise ValueError("ID destinasi harus unik")
    if cfg["focus"] not in ids:
        raise ValueError(f"focus '{cfg['focus']}' tidak ada di daftar destinasi")
    for c in cfg["competitors"]:
        if c not in ids:
            raise ValueError(f"competitor '{c}' tidak ada di daftar destinasi")
    for d in cfg["destinations"]:
        if not d.get("aliases"):
            raise ValueError(f"destinasi '{d['id']}' tidak punya alias")
    if not cfg["questions"]:
        raise ValueError("daftar pertanyaan kosong")


def destination_group(cfg: dict, dest_id: str) -> str:
    if dest_id == cfg["focus"]:
        return "focus"
    if dest_id in cfg["competitors"]:
        return "competitor"
    return "other"


def dest_name(cfg: dict, dest_id: str) -> str:
    for d in cfg["destinations"]:
        if d["id"] == dest_id:
            return d["name"]
    return dest_id


# ---------------------------------------------------------------------------
# Penghitungan sebutan (mention)
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    # Hanya NFKC (tanpa lowercase) supaya posisi highlight sama dengan teks asli;
    # pencocokan tidak peka huruf besar/kecil lewat re.IGNORECASE.
    return unicodedata.normalize("NFKC", text or "")


def alias_pattern(alias: str) -> str:
    parts = [re.escape(p) for p in normalize_text(alias).lower().split()]
    return r"[\s\-]+".join(parts)


def build_matchers(destinations: list) -> list:
    """Satu regex per destinasi; alias terpanjang dicoba lebih dulu sehingga
    'danau toba' dihitung satu kali, bukan dua (danau toba + toba)."""
    matchers = []
    for d in destinations:
        aliases = sorted({a for a in d["aliases"] if a.strip()}, key=lambda a: (-len(a), a))
        body = "|".join(alias_pattern(a) for a in aliases)
        matchers.append((d["id"], re.compile(r"(?<!\w)(?:" + body + r")(?!\w)", re.IGNORECASE)))
    return matchers


def scan_text(text: str, matchers: list) -> dict:
    """Kembalikan {dest_id: (jumlah_sebutan, posisi_pertama_atau_None)}."""
    norm = normalize_text(text)
    out = {}
    for dest_id, rx in matchers:
        hits = [m.start() for m in rx.finditer(norm)]
        out[dest_id] = (len(hits), hits[0] if hits else None)
    return out


def find_spans(text: str, matchers: list) -> list:
    """Rentang (start, end, dest_id) pada normalize_text(text), untuk highlight."""
    norm = normalize_text(text)
    spans = []
    for dest_id, rx in matchers:
        for m in rx.finditer(norm):
            spans.append((m.start(), m.end(), dest_id))
    spans.sort()
    merged, last_end = [], -1
    for s in spans:
        if s[0] >= last_end:
            merged.append(s)
            last_end = s[1]
    return merged


# ---------------------------------------------------------------------------
# HTTP & pemanggil API
# ---------------------------------------------------------------------------
class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body or ""


RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


def _retry_base() -> float:
    try:
        return float(os.environ.get("GEM_RETRY_BASE", "2"))
    except ValueError:
        return 2.0


def _error_message(resp) -> str:
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:300] or resp.reason or "tanpa pesan"
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or err)[:300]
        return str(err)[:300]
    return str(data)[:300]


def http_post_json(url: str, headers: dict, body: dict, timeout: float = 120.0, retries: int = 4) -> dict:
    import requests  # impor di sini agar --help tetap cepat

    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as exc:
            if attempt < retries:
                time.sleep(min(_retry_base() * (2 ** attempt), 30) + random.random() * 0.2)
                continue
            raise ProviderError(f"koneksi gagal: {exc.__class__.__name__}: {exc}") from exc
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise ProviderError("respons API bukan JSON", 200, resp.text[:500]) from exc
        msg = _error_message(resp)
        if resp.status_code in RETRY_STATUS and attempt < retries:
            delay = min(_retry_base() * (2 ** attempt), 30)
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    delay = min(float(ra), 60)
                except ValueError:
                    pass
            time.sleep(delay + random.random() * 0.2)
            continue
        raise ProviderError(f"HTTP {resp.status_code}: {msg}", resp.status_code, resp.text[:1000])
    raise ProviderError("gagal setelah beberapa percobaan")


def provider_base_url(provider: str, overrides: dict | None = None) -> str:
    info = PROVIDERS[provider]
    if overrides and overrides.get(provider):
        return overrides[provider].rstrip("/")
    if info.get("base_env") and os.environ.get(info["base_env"]):
        return os.environ[info["base_env"]].rstrip("/")
    return info["base_url"].rstrip("/")


def _claude_supports_effort(model: str) -> bool:
    return bool(re.match(r"claude-(opus|sonnet|fable|haiku|mythos)-5", model)
                or re.match(r"claude-(opus-4-[5678]|sonnet-4-6)", model))


def call_anthropic(model: str, prompt: str, key: str, opts: dict) -> tuple:
    url = provider_base_url("anthropic", opts.get("base_urls")) + "/v1/messages"
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    body = {"model": model, "max_tokens": int(opts.get("max_tokens") or 4000),
            "messages": [{"role": "user", "content": prompt}]}
    if _claude_supports_effort(model) and opts.get("claude_effort"):
        body["output_config"] = {"effort": opts["claude_effort"]}
    use_fallback = opts.get("claude_fallback", True) and model in CLAUDE_FALLBACK_MODELS
    if use_fallback:
        headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
        body["fallbacks"] = "default"
    timeout = opts.get("timeout", 180)
    try:
        data = http_post_json(url, headers, body, timeout)
    except ProviderError as exc:
        if use_fallback and exc.status == 400 and "fallback" in (str(exc) + exc.body).lower():
            headers.pop("anthropic-beta", None)
            body.pop("fallbacks", None)
            data = http_post_json(url, headers, body, timeout)
        else:
            raise
    stop = data.get("stop_reason")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if stop == "refusal":
        detail = (data.get("stop_details") or {}).get("category")
        raise ProviderError(f"model menolak menjawab (refusal{', ' + str(detail) if detail else ''})")
    usage = data.get("usage") or {}
    return text, {"stop_reason": stop, "input_tokens": usage.get("input_tokens"),
                  "output_tokens": usage.get("output_tokens")}


def call_gemini(model: str, prompt: str, key: str, opts: dict) -> tuple:
    url = f"{provider_base_url('gemini', opts.get('base_urls'))}/models/{model}:generateContent"
    headers = {"x-goog-api-key": key, "content-type": "application/json"}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if opts.get("max_tokens"):
        body["generationConfig"] = {"maxOutputTokens": int(opts["max_tokens"])}
    data = http_post_json(url, headers, body, opts.get("timeout", 180))
    cands = data.get("candidates") or []
    if not cands:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "tanpa kandidat")
        raise ProviderError(f"Gemini tidak mengembalikan jawaban ({reason})")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    usage = data.get("usageMetadata") or {}
    out_tokens = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return text, {"stop_reason": cands[0].get("finishReason"),
                  "input_tokens": usage.get("promptTokenCount"), "output_tokens": out_tokens or None}


def call_openai_compat(provider: str, model: str, prompt: str, key: str | None, opts: dict) -> tuple:
    url = provider_base_url(provider, opts.get("base_urls")) + "/chat/completions"
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    if provider == "openrouter":
        headers["x-title"] = "GEM Visibility Auditor"
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if opts.get("max_tokens"):
        # Model reasoning OpenAI memakai max_completion_tokens; endpoint kompatibel memakai max_tokens.
        body["max_completion_tokens" if provider == "openai" else "max_tokens"] = int(opts["max_tokens"])
    data = http_post_json(url, headers, body, opts.get("timeout", 180))
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError("respons tidak berisi 'choices'")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    usage = data.get("usage") or {}
    return content, {"stop_reason": choices[0].get("finish_reason"),
                     "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


# --- Mode demo: jawaban sintetis yang deterministik untuk menguji alur tanpa API.
_DEMO_LABELS = {
    "danau_toba": ("Danau Toba", "Lake Toba"), "bali": ("Bali", "Bali"),
    "labuan_bajo": ("Labuan Bajo", "Labuan Bajo"), "raja_ampat": ("Raja Ampat", "Raja Ampat"),
    "yogyakarta": ("Yogyakarta", "Yogyakarta"), "lombok": ("Lombok", "Lombok"),
    "bromo": ("Gunung Bromo", "Mount Bromo"), "likupang": ("Bunaken", "Bunaken"),
    "wakatobi": ("Wakatobi", "Wakatobi"), "belitung": ("Belitung", "Belitung"),
    "kelimutu": ("Danau Kelimutu", "Kelimutu"),
}
_DEMO_BASE = {
    "simulasi-a": {"bali": .95, "yogyakarta": .7, "labuan_bajo": .65, "raja_ampat": .6, "lombok": .55,
                   "bromo": .4, "danau_toba": .3, "likupang": .2, "wakatobi": .15, "belitung": .2, "kelimutu": .1},
    "simulasi-b": {"bali": .9, "yogyakarta": .6, "labuan_bajo": .7, "raja_ampat": .65, "lombok": .5,
                   "bromo": .45, "danau_toba": .45, "likupang": .25, "wakatobi": .2, "belitung": .15, "kelimutu": .15},
}
_DEMO_BOOST = {
    "Danau": {"danau_toba": .55, "kelimutu": .5},
    "Bahari": {"raja_ampat": .35, "wakatobi": .5, "likupang": .5, "labuan_bajo": .2},
    "Budaya": {"yogyakarta": .25, "danau_toba": .25},
    "Petualangan": {"bromo": .45, "lombok": .3},
    "Hidden gem": {"bali": -.5, "belitung": .4, "wakatobi": .35, "danau_toba": .15},
}
_DEMO_PHRASES = {
    "id": ["pemandangan alamnya luar biasa", "cocok untuk wisatawan pertama kali",
           "budaya lokalnya kuat dan ramah", "akses penerbangan semakin mudah",
           "pilihan akomodasi beragam", "ideal untuk fotografi dan relaksasi"],
    "en": ["the scenery is breathtaking", "great for first-time visitors",
           "the local culture is rich and welcoming", "flight access keeps improving",
           "there is a wide range of accommodation", "ideal for photography and relaxing"],
}


def call_demo(model: str, prompt: str, lang: str, category: str, run: int) -> tuple:
    seed = int(hashlib.sha256(f"{model}|{prompt}|{run}".encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    base = dict(_DEMO_BASE.get(model, _DEMO_BASE["simulasi-a"]))
    for k, v in _DEMO_BOOST.get(category, {}).items():
        base[k] = min(1.0, max(0.0, base.get(k, 0) + v))
    picked = [d for d, p in base.items() if rng.random() < p]
    if not picked:
        picked = ["bali"]
    picked.sort(key=lambda d: -base[d] + rng.random() * 0.6)
    picked = picked[:6]
    li = 0 if lang == "id" else 1
    intro = ("Berikut beberapa rekomendasi:" if li == 0 else "Here are some recommendations:")
    lines = [intro]
    for i, d in enumerate(picked, 1):
        label = _DEMO_LABELS.get(d, (d, d))[li]
        phrase = rng.choice(_DEMO_PHRASES["id" if li == 0 else "en"])
        lines.append(f"{i}. **{label}**: {phrase}.")
        if rng.random() < 0.3:
            lines.append(("   Banyak pelancong kembali lagi ke " if li == 0 else "   Many travelers return to ") + label + ".")
    lines.append("(Jawaban simulasi mode demo.)" if li == 0 else "(Simulated demo-mode answer.)")
    return "\n".join(lines), {"stop_reason": "demo", "input_tokens": None, "output_tokens": None}


def call_model(provider: str, model: str, prompt: str, key: str | None, opts: dict,
               lang: str = "id", category: str = "", run: int = 1) -> tuple:
    kind = PROVIDERS[provider]["kind"]
    if kind == "anthropic":
        return call_anthropic(model, prompt, key, opts)
    if kind == "gemini":
        return call_gemini(model, prompt, key, opts)
    if kind in ("openai", "openai_compat"):
        return call_openai_compat(provider, model, prompt, key, opts)
    if kind == "demo":
        return call_demo(model, prompt, lang, category, run)
    raise ValueError(f"provider tidak dikenal: {provider}")


# ---------------------------------------------------------------------------
# Kunci API
# ---------------------------------------------------------------------------
def load_dotenv_files() -> None:
    """Muat KEY=VALUE dari .env di folder kerja atau di samping .exe (tidak menimpa env)."""
    candidates = [Path.cwd() / ".env"]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    elif globals().get("__file__"):  # tidak ada __file__ saat ditempel ke sel Colab
        candidates.append(Path(globals()["__file__"]).resolve().parent / ".env")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("export "):
                    k = k[len("export "):].strip()
                v = v.strip().strip('"').strip("'")
                if k and v and k not in os.environ:
                    os.environ[k] = v
        except OSError:
            pass


def _colab_secret(name: str) -> str | None:
    if "google.colab" not in sys.modules:
        return None
    try:
        from google.colab import userdata  # type: ignore
        return userdata.get(name) or None
    except Exception:
        return None


def resolve_key(provider: str, explicit: dict | None = None) -> str | None:
    if explicit and explicit.get(provider):
        return explicit[provider]
    for name in PROVIDERS[provider]["env"]:
        if os.environ.get(name):
            return os.environ[name].strip()
        val = _colab_secret(name)
        if val:
            return val.strip()
    return None


def detect_available_providers() -> list:
    return [p for p in PROVIDERS if PROVIDERS[p]["env"] and resolve_key(p)]


def parse_model_specs(specs: list) -> list:
    """'anthropic' -> ('anthropic', model bawaan); 'gemini:gemini-2.5-pro' -> apa adanya."""
    out = []
    for raw in specs:
        for spec in str(raw).split(","):
            spec = spec.strip()
            if not spec:
                continue
            provider, _, model = spec.partition(":")
            provider = provider.strip().lower()
            if provider not in PROVIDERS:
                raise ValueError(f"provider '{provider}' tidak dikenal. Pilihan: {', '.join(PROVIDERS)}")
            model = model.strip() or PROVIDERS[provider]["default_model"]
            if (provider, model) not in out:
                out.append((provider, model))
    return out


# ---------------------------------------------------------------------------
# Menjalankan audit
# ---------------------------------------------------------------------------
def build_tasks(models: list, cfg: dict, languages: list, runs: int, max_questions: int = 0) -> list:
    questions = cfg["questions"][:max_questions] if max_questions else cfg["questions"]
    tasks = []
    for provider, model in models:
        for q in questions:
            for lang in languages:
                prompt = q["text"].get(lang)
                if not prompt:
                    continue
                for run in range(1, runs + 1):
                    tasks.append({
                        "response_id": f"{provider}:{model}|{q['qid']}|{lang}|{run}",
                        "provider": provider, "model": model, "model_label": f"{provider}:{model}",
                        "question_id": q["qid"], "category": q.get("category", ""),
                        "language": lang, "run": run, "prompt": prompt,
                    })
    return tasks


def run_one(task: dict, key: str | None, opts: dict) -> dict:
    rec = dict(task)
    rec["timestamp"] = _dt.datetime.now().isoformat(timespec="seconds")
    rec["simulated"] = PROVIDERS[task["provider"]]["kind"] == "demo"
    t0 = time.time()
    try:
        text, meta = call_model(task["provider"], task["model"], task["prompt"], key, opts,
                                task["language"], task["category"], task["run"])
        rec.update(response=text, status="ok" if text.strip() else "error",
                   error="" if text.strip() else "jawaban kosong", **meta)
    except Exception as exc:  # satu kegagalan tidak boleh menghentikan audit
        rec.update(response="", status="error", error=str(exc)[:500],
                   stop_reason=None, input_tokens=None, output_tokens=None)
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec


def run_audit(models: list, cfg: dict, languages=("id", "en"), runs: int = 1, max_questions: int = 0,
              keys: dict | None = None, opts: dict | None = None, workers: int = 4,
              progress=None, checkpoint_path: str | None = None, resume_records: list | None = None) -> list:
    """Jalankan semua pertanyaan ke semua model. Mengembalikan list record (dict)."""
    opts = dict(opts or {})
    tasks = build_tasks(models, cfg, list(languages), runs, max_questions)
    done_ok = {r["response_id"]: r for r in (resume_records or []) if r.get("status") == "ok"}
    pending = [t for t in tasks if t["response_id"] not in done_ok]
    resolved = {}
    for provider, _ in models:
        if PROVIDERS[provider].get("no_key"):
            resolved[provider] = None
        else:
            resolved[provider] = resolve_key(provider, keys)
    records = [done_ok[t["response_id"]] for t in tasks if t["response_id"] in done_ok]
    total = len(tasks)
    counter = {"n": len(records)}
    lock = threading.Lock()
    ck = open(checkpoint_path, "a", encoding="utf-8") if checkpoint_path else None

    def _work(task):
        key = resolved.get(task["provider"])
        if key is None and not PROVIDERS[task["provider"]].get("no_key"):
            rec = dict(task, timestamp=_dt.datetime.now().isoformat(timespec="seconds"), response="",
                       status="error", error="kunci API tidak ditemukan", latency_s=0.0,
                       stop_reason=None, input_tokens=None, output_tokens=None, simulated=False)
        else:
            rec = run_one(task, key, opts)
        with lock:
            records.append(rec)
            counter["n"] += 1
            if ck:
                ck.write(json.dumps(rec, ensure_ascii=False) + "\n")
                ck.flush()
            if progress:
                progress(counter["n"], total, rec)
        return rec

    try:
        if workers <= 1 or len(pending) <= 1:
            for t in pending:
                _work(t)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(_work, pending))
    finally:
        if ck:
            ck.close()
    order = {t["response_id"]: i for i, t in enumerate(tasks)}
    records.sort(key=lambda r: order.get(r["response_id"], 1 << 30))
    return records


def cli_progress(done: int, total: int, rec: dict) -> None:
    status = "ok " if rec["status"] == "ok" else "ERR"
    extra = "" if rec["status"] == "ok" else f"  {rec['error'][:120]}"
    log(f"[{done:>3}/{total}] {status} {rec['model_label']:<40} {rec['question_id']}-{rec['language']} "
        f"run{rec['run']} {rec.get('latency_s', 0):>5.1f}s{extra}")


# ---------------------------------------------------------------------------
# Analisis (Pandas)
# ---------------------------------------------------------------------------
def records_to_df(records: list):
    import pandas as pd
    df = pd.DataFrame(records)
    for col in RESPONSE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["response"] = df["response"].fillna("").astype(str)
    df["error"] = df["error"].fillna("").astype(str)
    return df[RESPONSE_COLUMNS + [c for c in df.columns if c not in RESPONSE_COLUMNS]]


def read_responses_csv(path: str):
    import pandas as pd
    df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False)
    if "model_label" not in df.columns or (df["model_label"] == "").all():
        df["model_label"] = df["provider"].astype(str) + ":" + df["model"].astype(str)
    if "response_id" not in df.columns:
        df["response_id"] = (df["model_label"] + "|" + df["question_id"].astype(str) + "|"
                             + df["language"].astype(str) + "|" + df["run"].astype(str))
    if "status" not in df.columns:
        df["status"] = "ok"
    return records_to_df(df.to_dict("records"))


def _sov_table(mentions, n_responses: int, cfg: dict):
    import pandas as pd
    order = {d["id"]: i for i, d in enumerate(cfg["destinations"])}
    g = mentions.groupby("destination_id").agg(
        mentions=("count", "sum"), responses_mentioned=("mentioned", "sum"))
    ranks = mentions.loc[mentions["mentioned"].astype(bool)].groupby("destination_id")["first_rank"].mean()
    g["avg_first_rank"] = ranks
    g = g.reindex([d["id"] for d in cfg["destinations"]]).fillna({"mentions": 0, "responses_mentioned": 0})
    total = g["mentions"].sum()
    g["share_of_voice_pct"] = (g["mentions"] / total * 100) if total else 0.0
    g["mention_rate_pct"] = (g["responses_mentioned"] / n_responses * 100) if n_responses else 0.0
    g = g.reset_index()
    g["destination"] = g["destination_id"].map(lambda d: dest_name(cfg, d))
    g["group"] = g["destination_id"].map(lambda d: destination_group(cfg, d))
    g["_o"] = g["destination_id"].map(order)
    g = g.sort_values(["share_of_voice_pct", "_o"], ascending=[False, True]).drop(columns="_o")
    g["rank"] = range(1, len(g) + 1)
    g["mentions"] = g["mentions"].astype(int)
    g["responses_mentioned"] = g["responses_mentioned"].astype(int)
    for c in ("share_of_voice_pct", "mention_rate_pct", "avg_first_rank"):
        g[c] = g[c].astype(float).round(2)
    return pd.DataFrame(g[["rank", "destination_id", "destination", "group", "mentions",
                           "responses_mentioned", "share_of_voice_pct", "mention_rate_pct",
                           "avg_first_rank"]])


def analyze(df, cfg: dict) -> dict:
    """Hitung sebutan per jawaban dan share of AI voice (keseluruhan, per bahasa, per model)."""
    import pandas as pd
    ok = df[df["status"] == "ok"]
    matchers = build_matchers(cfg["destinations"])
    rows = []
    for r in ok.to_dict("records"):
        hits = scan_text(r["response"], matchers)
        ranked = sorted((pos, d) for d, (cnt, pos) in hits.items() if cnt > 0)
        rank_of = {d: i + 1 for i, (_, d) in enumerate(ranked)}
        for d in cfg["destinations"]:
            cnt, _ = hits[d["id"]]
            rows.append({
                "response_id": r["response_id"], "provider": r["provider"], "model": r["model"],
                "model_label": r["model_label"], "question_id": r["question_id"],
                "category": r["category"], "language": r["language"], "run": r["run"],
                "destination_id": d["id"], "destination": d["name"],
                "group": destination_group(cfg, d["id"]), "count": int(cnt), "mentioned": cnt > 0,
                "first_rank": rank_of.get(d["id"]),
            })
    mentions = pd.DataFrame(rows, columns=[
        "response_id", "provider", "model", "model_label", "question_id", "category", "language",
        "run", "destination_id", "destination", "group", "count", "mentioned", "first_rank"])
    n_ok = len(ok)
    summary = _sov_table(mentions, n_ok, cfg) if n_ok else _sov_table(mentions.iloc[0:0], 0, cfg)

    def by(dim: str):
        parts = []
        for val, sub in mentions.groupby(dim, sort=False):
            n = sub["response_id"].nunique()
            t = _sov_table(sub, n, cfg)
            t.insert(0, dim, val)
            t.insert(1, "responses", n)
            parts.append(t)
        if not parts:
            return pd.DataFrame(columns=[dim, "responses"] + list(summary.columns))
        return pd.concat(parts, ignore_index=True)

    by_language = by("language")
    by_model = by("model_label")
    by_category = by("category")

    focus = cfg["focus"]
    srow = summary.set_index("destination_id")
    focus_sov = float(srow.loc[focus, "share_of_voice_pct"]) if n_ok else 0.0
    headline = {
        "focus_id": focus, "focus_name": dest_name(cfg, focus),
        "focus_sov_pct": focus_sov,
        "focus_rank": int(srow.loc[focus, "rank"]) if n_ok else None,
        "focus_mention_rate_pct": float(srow.loc[focus, "mention_rate_pct"]) if n_ok else 0.0,
        "destinations": len(cfg["destinations"]),
        "responses_ok": int(n_ok), "responses_total": int(len(df)),
        "responses_error": int((df["status"] != "ok").sum()),
        "models": sorted(df["model_label"].unique().tolist()),
        "simulated": bool(df["simulated"].astype(str).str.lower().isin(["true", "1"]).any()),
        "competitors": [],
    }
    for c in cfg["competitors"]:
        c_sov = float(srow.loc[c, "share_of_voice_pct"]) if n_ok else 0.0
        headline["competitors"].append({
            "id": c, "name": dest_name(cfg, c), "sov_pct": c_sov,
            "mention_rate_pct": float(srow.loc[c, "mention_rate_pct"]) if n_ok else 0.0,
            # Untuk setiap 100 sebutan kompetitor, fokus disebut sekian kali.
            "focus_per_100": round(focus_sov / c_sov * 100, 1) if c_sov else None,
        })
    return {"mentions": mentions, "summary": summary, "by_language": by_language,
            "by_model": by_model, "by_category": by_category, "headline": headline}


def headline_text(h: dict) -> str:
    lines = [f"{h['focus_name']}: share of AI voice {h['focus_sov_pct']:.1f}% "
             f"(peringkat {h['focus_rank']} dari {h['destinations']}), disebut di "
             f"{h['focus_mention_rate_pct']:.1f}% jawaban."]
    for c in h["competitors"]:
        ratio = f"{c['focus_per_100']:.1f}" if c["focus_per_100"] is not None else "-"
        lines.append(f"  vs {c['name']}: {c['sov_pct']:.1f}% SOV. Setiap 100 sebutan {c['name']}, "
                     f"{h['focus_name']} disebut {ratio} kali.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Grafik (Matplotlib)
# ---------------------------------------------------------------------------
def _mpl():
    import matplotlib
    if "ipykernel" not in sys.modules and "google.colab" not in sys.modules:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": COLORS["axis"],
        "axes.labelcolor": COLORS["ink2"], "xtick.color": COLORS["muted"], "ytick.color": COLORS["ink2"],
        "figure.facecolor": COLORS["surface"], "axes.facecolor": COLORS["surface"],
        "savefig.facecolor": COLORS["surface"],
    })
    return plt


def _style_axes(ax, grid_axis: str = "x") -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(COLORS["axis"])
    ax.spines["bottom"].set_color(COLORS["axis"])
    ax.grid(axis=grid_axis, color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _subtitle(h: dict) -> str:
    sim = "  |  DATA SIMULASI (mode demo)" if h.get("simulated") else ""
    return f"{h['responses_ok']} jawaban dari {len(h['models'])} model{sim}"


def fig_share_of_voice(results: dict):
    plt = _mpl()
    s = results["summary"].iloc[::-1]
    h = results["headline"]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(s) + 1.6))
    colors = [COLORS[g] for g in s["group"]]
    ax.barh(s["destination"], s["share_of_voice_pct"], color=colors, height=0.6)
    xmax = max(float(s["share_of_voice_pct"].max() or 0), 1.0)
    for y, v in enumerate(s["share_of_voice_pct"]):
        ax.text(v + xmax * 0.01, y, f"{v:.1f}%", va="center", fontsize=9, color=COLORS["ink"])
    ax.set_xlim(0, xmax * 1.15)
    ax.set_xlabel("Share of AI voice (% dari seluruh sebutan destinasi)")
    _style_axes(ax, "x")
    for lbl in ax.get_yticklabels():
        if lbl.get_text() == h["focus_name"]:
            lbl.set_fontweight("bold")
            lbl.set_color(COLORS["ink"])
    from matplotlib.patches import Patch
    handles = [Patch(color=COLORS[g], label=GROUP_LABELS[g]) for g in ("focus", "competitor", "other")]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9)
    fig.suptitle("Share of AI voice: destinasi wisata Indonesia", x=0.02, ha="left",
                 fontsize=13, fontweight="bold", color=COLORS["ink"])
    ax.set_title(_subtitle(h), loc="left", fontsize=9, color=COLORS["ink2"])
    fig.tight_layout()
    return fig


def fig_by_language(results: dict):
    plt = _mpl()
    import numpy as np
    bl = results["by_language"]
    h = results["headline"]
    order = results["summary"]["destination"].tolist()[::-1]
    langs = [lang for lang in ("id", "en") if lang in set(bl["language"])] + \
            sorted(set(bl["language"]) - {"id", "en"})
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(order) + 1.8))
    y = np.arange(len(order))
    bh = 0.36 if len(langs) > 1 else 0.6
    palette = [COLORS["lang_id"], COLORS["lang_en"], "#1baf7a", "#6250d6"]
    for i, lang in enumerate(langs):
        sub = bl[bl["language"] == lang].set_index("destination").reindex(order)
        vals = sub["share_of_voice_pct"].fillna(0).values
        offset = ((len(langs) - 1) / 2 - i) * bh  # bahasa pertama di atas
        ax.barh(y + offset, vals, height=bh * 0.92, color=palette[i % len(palette)],
                label=LANG_LABELS.get(lang, lang))
    ax.set_yticks(y, order)
    ax.set_xlabel("Share of AI voice (%)")
    _style_axes(ax, "x")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.suptitle("Share of AI voice per bahasa pertanyaan", x=0.02, ha="left",
                 fontsize=13, fontweight="bold", color=COLORS["ink"])
    ax.set_title(_subtitle(h), loc="left", fontsize=9, color=COLORS["ink2"])
    fig.tight_layout()
    return fig


def fig_by_model(results: dict):
    plt = _mpl()
    from matplotlib.colors import LinearSegmentedColormap
    bm = results["by_model"]
    h = results["headline"]
    order = results["summary"]["destination"].tolist()
    models = sorted(bm["model_label"].unique().tolist())
    piv = bm.pivot_table(index="destination", columns="model_label", values="share_of_voice_pct",
                         aggfunc="first").reindex(index=order, columns=models).fillna(0)
    cmap = LinearSegmentedColormap.from_list("seq", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
    fig, ax = plt.subplots(figsize=(max(6.5, 1.9 * len(models) + 3.5), 0.42 * len(order) + 1.9))
    vmax = max(float(piv.values.max()), 1.0)
    ax.imshow(piv.values, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            ax.text(j, i, f"{v:.1f}%", ha="center", va="center", fontsize=9,
                    color="#ffffff" if v > vmax * 0.55 else COLORS["ink"])
    ax.set_xticks(range(len(models)), [m.replace(":", ":\n", 1) for m in models], fontsize=8.5)
    ax.set_yticks(range(len(order)), order)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.suptitle("Share of AI voice per model", x=0.02, ha="left", fontsize=13,
                 fontweight="bold", color=COLORS["ink"])
    ax.set_title(_subtitle(h), loc="left", fontsize=9, color=COLORS["ink2"])
    fig.tight_layout()
    return fig


def fig_mention_rate(results: dict):
    plt = _mpl()
    s = results["summary"].sort_values("mention_rate_pct").copy()
    h = results["headline"]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(s) + 1.6))
    ax.barh(s["destination"], s["mention_rate_pct"], color=[COLORS[g] for g in s["group"]], height=0.6)
    for y, v in enumerate(s["mention_rate_pct"]):
        ax.text(v + 1, y, f"{v:.0f}%", va="center", fontsize=9, color=COLORS["ink"])
    ax.set_xlim(0, 112)
    ax.set_xlabel("% jawaban yang menyebut destinasi")
    _style_axes(ax, "x")
    fig.suptitle("Mention rate: seberapa sering destinasi muncul", x=0.02, ha="left",
                 fontsize=13, fontweight="bold", color=COLORS["ink"])
    ax.set_title(_subtitle(h), loc="left", fontsize=9, color=COLORS["ink2"])
    fig.tight_layout()
    return fig


CHARTS = {
    "share_of_voice.png": fig_share_of_voice,
    "sov_by_language.png": fig_by_language,
    "sov_by_model.png": fig_by_model,
    "mention_rate.png": fig_mention_rate,
}


def save_charts(results: dict, out_dir: Path, show: bool = False) -> dict:
    plt = _mpl()
    paths = {}
    for name, fn in CHARTS.items():
        fig = fn(results)
        p = out_dir / name
        fig.savefig(p, dpi=150)
        paths[name] = p
        if show:  # notebook/Colab: tampilkan PNG inline (tidak bergantung backend matplotlib)
            try:
                from IPython.display import Image, display  # type: ignore
                display(Image(filename=str(p)))
            except Exception:
                plt.show()
        plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
# Laporan HTML & ekspor
# ---------------------------------------------------------------------------
def _highlight_html(text: str, matchers: list, cfg: dict) -> str:
    norm = normalize_text(text)
    out, pos = [], 0
    for s, e, d in find_spans(text, matchers):
        out.append(html.escape(norm[pos:s]))
        cls = destination_group(cfg, d)
        out.append(f'<mark class="{cls}" title="{html.escape(dest_name(cfg, d))}">{html.escape(norm[s:e])}</mark>')
        pos = e
    out.append(html.escape(norm[pos:]))
    return "".join(out)


def build_report_html(results: dict, df, cfg: dict, chart_paths: dict) -> str:
    h = results["headline"]
    imgs = {}
    for name, p in chart_paths.items():
        imgs[name] = base64.b64encode(Path(p).read_bytes()).decode("ascii")
    s = results["summary"]
    rows = "".join(
        f"<tr class='{r.group}'><td>{r.rank}</td><td><span class='sw {r.group}'></span>{html.escape(r.destination)}</td>"
        f"<td>{r.mentions}</td><td>{r.responses_mentioned}</td><td>{r.share_of_voice_pct:.1f}%</td>"
        f"<td>{r.mention_rate_pct:.1f}%</td><td>{'' if r.avg_first_rank != r.avg_first_rank else f'{r.avg_first_rank:.2f}'}</td></tr>"
        for r in s.itertuples())
    comp_tiles = "".join(
        f"<div class='tile'><div class='lbl'>{html.escape(c['name'])}</div><div class='val'>{c['sov_pct']:.1f}%</div>"
        f"<div class='sub'>{html.escape(h['focus_name'])} disebut {c['focus_per_100'] if c['focus_per_100'] is not None else '-'} "
        f"kali per 100 sebutan {html.escape(c['name'])}</div></div>" for c in h["competitors"])
    matchers = build_matchers(cfg["destinations"])
    ok = df[df["status"] == "ok"]
    samples = []
    for r in ok.head(40).to_dict("records"):
        samples.append(
            f"<details><summary><b>{html.escape(r['model_label'])}</b> | {html.escape(str(r['question_id']))}-"
            f"{html.escape(str(r['language']))} | {html.escape(r['prompt'])}</summary>"
            f"<pre>{_highlight_html(r['response'], matchers, cfg)}</pre></details>")
    errors = df[df["status"] != "ok"]
    err_html = ""
    if len(errors):
        err_rows = "".join(f"<tr><td>{html.escape(r['model_label'])}</td><td>{html.escape(str(r['question_id']))}-"
                           f"{html.escape(str(r['language']))}</td><td>{html.escape(r['error'])}</td></tr>"
                           for r in errors.head(50).to_dict("records"))
        err_html = (f"<h2>Permintaan gagal ({len(errors)})</h2><table><tr><th>Model</th><th>Pertanyaan</th>"
                    f"<th>Error</th></tr>{err_rows}</table>")
    sim_banner = ("<div class='banner'>Mode demo: semua jawaban adalah SIMULASI offline, bukan keluaran "
                  "LLM sungguhan. Jalankan dengan kunci API untuk audit nyata.</div>") if h["simulated"] else ""
    img_tags = "".join(f"<figure><img alt='{n}' src='data:image/png;base64,{b}'></figure>" for n, b in imgs.items())
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GEM Visibility Audit</title>
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9;
--focus:#2a78d6;--competitor:#eb6834;--other:#c3c2b7;--warn-bg:#fff4dc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--line:#2c2c2a;--focus:#3987e5;--competitor:#d95926;--other:#5f5e5a;--warn-bg:#3a2e12}}
figure img{{filter:brightness(.92)}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:18px;margin:32px 0 12px}}
.meta{{color:var(--ink2);font-size:13px}}
.banner{{background:var(--warn-bg);border:1px solid var(--line);padding:10px 14px;border-radius:8px;margin:16px 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:16px}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.tile .lbl{{color:var(--ink2);font-size:13px}} .tile .val{{font-size:30px;font-weight:600}}
.tile.hero .val{{font-size:48px}} .tile .sub{{color:var(--ink2);font-size:12.5px}}
figure{{margin:16px 0;background:#fcfcfb;border:1px solid var(--line);border-radius:10px;padding:8px;overflow:auto}}
figure img{{max-width:100%;height:auto;display:block;margin:auto}}
table{{border-collapse:collapse;width:100%;background:var(--surface);font-size:14px}}
th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}} th{{color:var(--ink2);font-weight:600}}
td:nth-child(n+3){{font-variant-numeric:tabular-nums}}
.sw{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px;background:var(--other)}}
.sw.focus{{background:var(--focus)}} .sw.competitor{{background:var(--competitor)}}
tr.focus td{{font-weight:600}}
.tablewrap{{overflow-x:auto}}
details{{background:var(--surface);border:1px solid var(--line);border-radius:8px;margin:8px 0;padding:8px 12px}}
summary{{cursor:pointer;font-size:13.5px}} pre{{white-space:pre-wrap;font:13px/1.5 ui-monospace,Consolas,monospace}}
mark{{background:#e1e0d9;color:inherit;border-radius:3px;padding:0 2px}}
mark.focus{{background:#cde2fb;color:#0b0b0b}} mark.competitor{{background:#fbd9c9;color:#0b0b0b}}
</style></head><body><main>
<h1>GEM Visibility Audit: share of AI voice</h1>
<div class="meta">Dibuat {generated} | GEM Visibility Auditor v{__version__} | {h['responses_ok']} jawaban berhasil,
{h['responses_error']} gagal | Model: {html.escape(', '.join(h['models']))}</div>
{sim_banner}
<div class="tiles">
<div class="tile hero"><div class="lbl">Share of AI voice {html.escape(h['focus_name'])}</div>
<div class="val">{h['focus_sov_pct']:.1f}%</div><div class="sub">Peringkat {h['focus_rank']} dari {h['destinations']} destinasi,
disebut di {h['focus_mention_rate_pct']:.1f}% jawaban</div></div>
{comp_tiles}
</div>
<h2>Grafik</h2>
{img_tags}
<h2>Ringkasan per destinasi</h2>
<div class="tablewrap"><table><tr><th>#</th><th>Destinasi</th><th>Sebutan</th><th>Jawaban yang menyebut</th>
<th>Share of voice</th><th>Mention rate</th><th>Rata-rata urutan pertama</th></tr>{rows}</table></div>
<p class="meta">Share of voice = sebutan destinasi / total sebutan semua destinasi. Mention rate = % jawaban
yang menyebut destinasi minimal sekali. Urutan pertama = posisi destinasi saat pertama kali disebut di
jawaban (1 = paling awal).</p>
{err_html}
<h2>Contoh jawaban (sorotan: biru = fokus, oranye = kompetitor)</h2>
{''.join(samples)}
</main></body></html>"""


def export_outputs(df, results: dict, cfg: dict, out_dir: Path, show_charts: bool = False,
                   meta: dict | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    tables = {
        "responses.csv": df,
        "mentions.csv": results["mentions"],
        "summary.csv": results["summary"],
        "sov_by_language.csv": results["by_language"],
        "sov_by_model.csv": results["by_model"],
        "sov_by_category.csv": results["by_category"],
    }
    for name, t in tables.items():
        p = out_dir / name
        t.to_csv(p, index=False, encoding="utf-8-sig")
        paths[name] = p
    if results["headline"]["responses_ok"]:
        paths.update(save_charts(results, out_dir, show=show_charts))
    else:
        log("Tidak ada jawaban yang berhasil: grafik tidak dibuat. Periksa kunci API dan pesan error.")
    report = out_dir / "report.html"
    report.write_text(build_report_html(results, df, cfg, {k: v for k, v in paths.items() if k.endswith(".png")}),
                      encoding="utf-8")
    paths["report.html"] = report
    dash = {
        "meta": dict(meta or {}, tool="GEM Visibility Auditor", version=__version__,
                     generated=_dt.datetime.now().isoformat(timespec="seconds")),
        "config": cfg,
        "headline": results["headline"],
        "responses": json.loads(df.to_json(orient="records", force_ascii=False)),
    }
    dpath = out_dir / "dashboard_data.json"
    dpath.write_text(json.dumps(dash, ensure_ascii=False, indent=1), encoding="utf-8")
    paths["dashboard_data.json"] = dpath
    return paths


def zip_outputs(out_dir: Path) -> Path:
    zpath = out_dir.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.iterdir()):
            if p.is_file():
                zf.write(p, arcname=f"{out_dir.name}/{p.name}")
    return zpath


def print_summary(results: dict) -> None:
    s = results["summary"]
    log("")
    log("=" * 78)
    log(f"{'#':>2}  {'Destinasi':<26}{'Sebutan':>8}{'SOV %':>9}{'Mention %':>11}{'Urutan':>8}")
    log("-" * 78)
    for r in s.itertuples():
        star = "*" if r.group == "focus" else ("+" if r.group == "competitor" else " ")
        rank = "" if r.avg_first_rank != r.avg_first_rank else f"{r.avg_first_rank:.2f}"
        log(f"{r.rank:>2}{star} {r.destination:<26}{r.mentions:>8}{r.share_of_voice_pct:>9.1f}"
            f"{r.mention_rate_pct:>11.1f}{rank:>8}")
    log("-" * 78)
    log("* fokus, + kompetitor utama")
    log(headline_text(results["headline"]))
    if results["headline"]["simulated"]:
        log("CATATAN: ada data SIMULASI (mode demo), bukan jawaban LLM sungguhan.")
    log("=" * 78)


# ---------------------------------------------------------------------------
# Alur utama
# ---------------------------------------------------------------------------
def execute(models: list, cfg: dict, languages: list, runs: int, max_questions: int, out_root: str,
            keys: dict | None = None, opts: dict | None = None, workers: int = 4,
            show_charts: bool = False, resume_dir: str | None = None, out_dir: str | None = None) -> tuple:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path(out_dir) if out_dir else Path(out_root) / f"audit_{stamp}"
    resume_records = []
    if resume_dir:
        target = Path(resume_dir)
        ck = target / "responses.jsonl"
        if ck.is_file():
            resume_records = [json.loads(line) for line in ck.read_text(encoding="utf-8").splitlines() if line.strip()]
            log(f"Melanjutkan: {sum(1 for r in resume_records if r.get('status') == 'ok')} jawaban sudah ada.")
    target.mkdir(parents=True, exist_ok=True)
    n_tasks = len(build_tasks(models, cfg, languages, runs, max_questions))
    log(f"Model: {', '.join(f'{p}:{m}' for p, m in models)}")
    log(f"Bahasa: {', '.join(languages)} | runs: {runs} | total permintaan: {n_tasks}")
    if any(PROVIDERS[p]["kind"] == "demo" for p, _ in models):
        log("MODE DEMO: jawaban disimulasikan secara offline (bukan data nyata).")
    log(f"Folder hasil: {target.resolve()}")
    log("")
    records = run_audit(models, cfg, languages, runs, max_questions, keys, opts, workers,
                        progress=cli_progress, checkpoint_path=str(target / "responses.jsonl"),
                        resume_records=resume_records)
    df = records_to_df(records)
    results = analyze(df, cfg)
    meta = {"models": [f"{p}:{m}" for p, m in models], "languages": languages, "runs": runs}
    paths = export_outputs(df, results, cfg, target, show_charts=show_charts, meta=meta)
    print_summary(results)
    log(f"\nFile hasil di: {target.resolve()}")
    for name in ("report.html", "responses.csv", "summary.csv", "share_of_voice.png", "dashboard_data.json"):
        if name in paths:
            log(f"  - {paths[name].name}")
    return target, results, df


def _in_notebook() -> bool:
    if "google.colab" in sys.modules:
        return True
    try:
        shell = get_ipython().__class__.__name__  # type: ignore[name-defined]  # noqa: F821
        return shell in ("ZMQInteractiveShell", "Shell")
    except NameError:
        return False


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt)
    except (EOFError, KeyboardInterrupt, Exception):
        return default
    return val.strip() or default


def _ask_secret(prompt: str) -> str:
    try:
        import getpass
        return getpass.getpass(prompt).strip()
    except Exception:
        return ""


def _choose_models_interactively(non_interactive: bool) -> tuple:
    """Kembalikan (models, keys). Dipakai oleh wizard .exe dan Colab."""
    keys = {}
    detected = detect_available_providers()
    if detected:
        log(f"Kunci API terdeteksi untuk: {', '.join(detected)}")
    if non_interactive:
        return (parse_model_specs(detected) if detected else [("demo", "simulasi-a"), ("demo", "simulasi-b")]), keys
    log("Provider: " + ", ".join(p for p in PROVIDERS))
    default = ",".join(detected) if detected else "demo"
    ans = _ask(f"Pilih provider/model, pisahkan koma (Enter = {default}): ", default)
    models = parse_model_specs([ans])
    if any(p == "demo" for p, _ in models) and len(models) == 1 and models[0][1] == "simulasi-a":
        models.append(("demo", "simulasi-b"))
    for p, _ in models:
        if PROVIDERS[p].get("no_key") or resolve_key(p):
            continue
        k = _ask_secret(f"Masukkan {PROVIDERS[p]['env'][0]} (input tersembunyi, Enter = lewati): ")
        if k:
            keys[p] = k
    models = [(p, m) for p, m in models if PROVIDERS[p].get("no_key") or resolve_key(p, keys)]
    if not models:
        log("Tidak ada kunci API. Menjalankan mode demo (simulasi).")
        models = [("demo", "simulasi-a"), ("demo", "simulasi-b")]
    return models, keys


def notebook_main(settings: dict | None = None) -> tuple:
    """Titik masuk untuk Google Colab / Jupyter (file ditempel ke satu sel)."""
    st = dict(NOTEBOOK_SETTINGS, **(settings or {}))
    load_dotenv_files()
    cfg = load_config()
    non_interactive = os.environ.get("GEM_NONINTERACTIVE") == "1" or not st["ask_for_keys"]
    log(f"GEM Visibility Auditor v{__version__} (mode notebook)")
    if st["models"]:
        models, keys = parse_model_specs(st["models"]), {}
        for p, _ in models:
            if not PROVIDERS[p].get("no_key") and not resolve_key(p) and not non_interactive:
                k = _ask_secret(f"Masukkan {PROVIDERS[p]['env'][0]}: ")
                if k:
                    keys[p] = k
    else:
        models, keys = _choose_models_interactively(non_interactive)
    target, results, df = execute(models, cfg, st["languages"], int(st["runs"]), int(st["max_questions"]),
                                  st["output_dir"], keys=keys, opts={"claude_effort": "low"}, show_charts=True)
    try:
        from IPython.display import display  # type: ignore
        display(results["summary"])
    except Exception:
        pass
    zpath = zip_outputs(target)
    log(f"Arsip hasil: {zpath}")
    if st.get("download_zip") and "google.colab" in sys.modules:
        try:
            from google.colab import files  # type: ignore
            files.download(str(zpath))
        except Exception as exc:
            log(f"(Unduh otomatis gagal: {exc}. Ambil file dari panel Files.)")
    return target, results, df


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gem_visibility_auditor",
        description="GEM Visibility Auditor: ukur share of AI voice destinasi wisata di jawaban LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Contoh:\n  gem_visibility_auditor --demo\n"
               "  gem_visibility_auditor --models anthropic gemini openai --runs 2\n"
               "  gem_visibility_auditor --models anthropic:claude-opus-5-5 groq ollama:llama3.1\n"
               "  gem_visibility_auditor --analyze hasil/responses.csv --out hasil_ulang",
    )
    p.add_argument("--models", nargs="+", help="provider atau provider:model (" + ", ".join(PROVIDERS) + ")")
    p.add_argument("--demo", action="store_true", help="mode simulasi offline (tanpa kunci API)")
    p.add_argument("--langs", nargs="+", default=["id", "en"], help="bahasa pertanyaan (bawaan: id en)")
    p.add_argument("--runs", type=int, default=1, help="pengulangan per pertanyaan (bawaan: 1)")
    p.add_argument("--max-questions", type=int, default=0, help="batasi jumlah topik (0 = semua)")
    p.add_argument("--config", help="file JSON berisi destinations/questions/focus/competitors")
    p.add_argument("--out", help="folder hasil (bawaan: gem_audit_output/audit_<waktu>)")
    p.add_argument("--out-root", default="gem_audit_output", help="folder induk hasil")
    p.add_argument("--workers", type=int, default=4, help="permintaan paralel (bawaan: 4)")
    p.add_argument("--timeout", type=float, default=180, help="timeout per permintaan, detik")
    p.add_argument("--max-tokens", type=int, default=0, help="batas token output (Claude bawaan 4000)")
    p.add_argument("--claude-effort", default="low", choices=["low", "medium", "high", "xhigh", "max"],
                   help="effort Claude (bawaan: low, hemat biaya)")
    p.add_argument("--no-claude-fallback", action="store_true", help="matikan server-side fallback Claude")
    p.add_argument("--base-url", action="append", default=[], metavar="PROVIDER=URL",
                   help="ganti endpoint, mis. ollama=http://192.168.1.5:11434/v1")
    p.add_argument("--key", action="append", default=[], metavar="PROVIDER=KEY",
                   help="kunci API langsung (lebih aman lewat env/.env)")
    p.add_argument("--resume", metavar="FOLDER", help="lanjutkan audit yang terputus di folder ini")
    p.add_argument("--analyze", metavar="RESPONSES_CSV", help="analisis ulang responses.csv tanpa memanggil API")
    p.add_argument("--list-questions", action="store_true", help="tampilkan daftar pertanyaan lalu keluar")
    p.add_argument("--export-config", metavar="FILE", help="tulis konfigurasi bawaan ke JSON lalu keluar")
    p.add_argument("--zip", action="store_true", help="buat arsip .zip dari folder hasil")
    p.add_argument("--open", dest="open_report", action="store_true", help="buka report.html di browser")
    p.add_argument("--no-open", action="store_true", help="jangan buka browser (wizard)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _kv_list(items: list, what: str) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"Format {what} salah: '{it}', gunakan PROVIDER=NILAI")
        k, v = it.split("=", 1)
        k = k.strip().lower()
        if k not in PROVIDERS:
            raise SystemExit(f"provider '{k}' tidak dikenal")
        out[k] = v.strip()
    return out


def _pause_if_double_clicked(wizard: bool) -> None:
    if wizard and getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        _ask("\nTekan Enter untuk menutup jendela...")


def main(argv: list | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # konsol Windows lama (cp1252)
        except Exception:
            pass
    if argv is None and _in_notebook():
        notebook_main()
        return 0
    raw = sys.argv[1:] if argv is None else argv
    args = build_arg_parser().parse_args(raw)
    load_dotenv_files()
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError, KeyError) as exc:
        log(f"Konfigurasi tidak valid: {exc}")
        return 2

    if args.export_config:
        Path(args.export_config).parent.mkdir(parents=True, exist_ok=True)
        Path(args.export_config).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Konfigurasi ditulis ke {args.export_config}")
        return 0
    if args.list_questions:
        for q in cfg["questions"]:
            for lang, t in q["text"].items():
                log(f"{q['qid']}-{lang} [{q.get('category', '')}] {t}")
        return 0
    if args.analyze:
        df = read_responses_csv(args.analyze)
        results = analyze(df, cfg)
        target = Path(args.out or (Path(args.out_root) / ("analisis_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))))
        export_outputs(df, results, cfg, target, meta={"source": str(args.analyze)})
        print_summary(results)
        log(f"\nFile hasil di: {target.resolve()}")
        return 0

    wizard = not raw and sys.stdin is not None and sys.stdin.isatty()
    keys = _kv_list(args.key, "--key")
    base_urls = _kv_list(args.base_url, "--base-url")
    log(f"GEM Visibility Auditor v{__version__}")
    try:
        if args.demo:
            models = [("demo", "simulasi-a"), ("demo", "simulasi-b")]
        elif args.models:
            models = parse_model_specs(args.models)
        else:
            models, wiz_keys = _choose_models_interactively(non_interactive=not wizard)
            keys.update(wiz_keys)
    except ValueError as exc:
        log(str(exc))
        return 2
    missing = [p for p, _ in models if not PROVIDERS[p].get("no_key") and not resolve_key(p, keys)]
    if missing:
        log(f"Kunci API tidak ditemukan untuk: {', '.join(sorted(set(missing)))}. Set environment variable "
            f"({', '.join(PROVIDERS[m]['env'][0] for m in sorted(set(missing)))}) atau pakai --key.")
        return 2
    runs, langs = args.runs, args.langs
    if wizard:
        try:
            runs = max(1, int(_ask(f"Pengulangan per pertanyaan (Enter = {runs}): ", str(runs))))
        except ValueError:
            pass
        langs = _ask("Bahasa, pisahkan koma (Enter = id,en): ", "id,en").replace(" ", "").split(",")
    opts = {"timeout": args.timeout, "max_tokens": args.max_tokens or None, "claude_effort": args.claude_effort,
            "claude_fallback": not args.no_claude_fallback, "base_urls": base_urls}
    try:
        target, results, df = execute(models, cfg, langs, runs, args.max_questions, args.out_root, keys=keys,
                                      opts=opts, workers=args.workers, resume_dir=args.resume, out_dir=args.out)
    except KeyboardInterrupt:
        log("\nDihentikan. Jawaban yang sudah masuk tersimpan di responses.jsonl (pakai --resume).")
        return 130
    if args.zip:
        log(f"Arsip: {zip_outputs(target)}")
    if (wizard and not args.no_open) or args.open_report:
        try:
            webbrowser.open((target / "report.html").resolve().as_uri())
        except Exception:
            pass
    _pause_if_double_clicked(wizard)
    return 0 if results["headline"]["responses_ok"] > 0 else 1


if __name__ == "__main__":
    _rc = main()
    if not _in_notebook():
        sys.exit(_rc)
