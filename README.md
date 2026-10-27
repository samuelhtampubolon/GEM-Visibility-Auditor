# GEM Visibility Auditor

Prototipe audit visibilitas untuk pilar **GEM (Generative Engine Marketing)**, marketing intelligence pariwisata.
Program menembakkan **30 pertanyaan wisata** (15 topik, masing-masing dalam Bahasa Indonesia dan Inggris) ke API LLM
(Claude, Gemini, ChatGPT, Groq, DeepSeek, OpenRouter, Mistral, Ollama), lalu menghitung **berapa kali Danau Toba
disebut dibanding Bali, Labuan Bajo**, dan 8 destinasi lain. Hasilnya: CSV, grafik **"share of AI voice"**
(Pandas + Matplotlib), laporan HTML, dashboard Streamlit, dan dashboard web di GitHub Pages.

| Cara pakai | Perintah / tautan |
|---|---|
| Dashboard web (GitHub Pages) | https://samuelhtampubolon.github.io/GEM-Visibility-Auditor/ |
| Google Colab | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/samuelhtampubolon/GEM-Visibility-Auditor/blob/main/GEM_Visibility_Auditor_Colab.ipynb) atau salin seluruh isi `gem_visibility_auditor.py` ke **satu sel** |
| Windows .exe | unduh dari [Releases](https://github.com/samuelhtampubolon/GEM-Visibility-Auditor/releases/latest), klik dua kali |
| Python lokal | `python gem_visibility_auditor.py --models anthropic gemini openai` |
| Dashboard Streamlit | `streamlit run streamlit_app.py` (atau deploy ke Streamlit Community Cloud) |

---

## 1. Google Colab (copy-paste satu sel)

**Cara tercepat:** klik [Open in Colab](https://colab.research.google.com/github/samuelhtampubolon/GEM-Visibility-Auditor/blob/main/GEM_Visibility_Auditor_Colab.ipynb) lalu *Runtime > Run all*. Notebook itu berisi satu sel
yang identik dengan `gem_visibility_auditor.py` (diuji otomatis). Cara manual:

1. Buka https://colab.research.google.com, buat notebook baru.
2. (Opsional) Klik ikon kunci (**Secrets**) di panel kiri, tambahkan `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
   dan/atau `OPENAI_API_KEY`, lalu aktifkan *Notebook access*.
3. Buka [`gem_visibility_auditor.py`](gem_visibility_auditor.py), klik **Raw**, salin **seluruh isi** ke **satu sel**,
   tekan **Shift+Enter**.
4. Program mendeteksi kunci dari Secrets. Bila tidak ada, Anda ditanya provider dan kunci (input tersembunyi).
   Enter kosong = mode demo (simulasi).
5. Tabel ringkasan dan 4 grafik tampil langsung di bawah sel; folder hasil diunduh otomatis sebagai `.zip`.

Pengaturan Colab (model, bahasa, jumlah pengulangan) ada di variabel `NOTEBOOK_SETTINGS` di bagian atas file.
Pandas, Matplotlib, dan Requests sudah terpasang di Colab, tidak perlu `pip install`.

## 2. Windows .exe

**Unduh langsung:** halaman [Releases](https://github.com/samuelhtampubolon/GEM-Visibility-Auditor/releases/latest)
berisi `GEM-Visibility-Auditor.exe` (CLI + wizard) dan `GEM-Dashboard.exe` (dashboard Streamlit). Keduanya dibangun
dan diuji otomatis oleh GitHub Actions di Windows (`.github/workflows/build-exe.yml`). Hasil build tiap commit juga
tersedia sebagai *artifact* di tab Actions.

* Klik dua kali `GEM-Visibility-Auditor.exe`: wizard bertanya provider, kunci API, pengulangan, dan bahasa,
  lalu membuka `report.html` di browser.
* Dari terminal: `GEM-Visibility-Auditor.exe --demo` atau `GEM-Visibility-Auditor.exe --models anthropic gemini`.
* Kunci API dibaca dari environment variable atau file `.env` di folder yang sama dengan .exe (lihat `.env.example`),
  atau diketik di wizard (input tersembunyi). Kunci sengaja **tidak** bisa diberikan lewat argumen baris perintah.
* Verifikasi unduhan: bandingkan SHA-256 file dengan `SHA256SUMS.txt` di halaman rilis
  (PowerShell: `Get-FileHash .\GEM-Visibility-Auditor.exe`). File belum ditandatangani kode, jadi SmartScreen bisa
  memberi peringatan.
* Rilis tidak pernah ditimpa. Rilis baru dibuat otomatis saat `__version__` di `gem_visibility_auditor.py` dinaikkan.

**Build sendiri** (perintah persisnya juga ada di header masing-masing file):

```bash
pip install pyinstaller pandas matplotlib requests
pyinstaller --onefile --name GEM-Visibility-Auditor gem_visibility_auditor.py
# hasil: dist/GEM-Visibility-Auditor.exe

# Dashboard sebagai .exe (opsional, bila suatu saat dibutuhkan)
pip install pyinstaller streamlit pandas matplotlib requests
pyinstaller --onefile --name GEM-Dashboard --collect-all streamlit --copy-metadata streamlit --add-data "streamlit_app.py:." --add-data "gem_visibility_auditor.py:." --hidden-import gem_visibility_auditor dashboard_launcher.py
# hasil: dist/GEM-Dashboard.exe, membuka http://localhost:8501
```

## 3. Python lokal

```bash
pip install -r requirements.txt
python gem_visibility_auditor.py --demo                       # uji alur tanpa kunci API (simulasi)
python gem_visibility_auditor.py                              # wizard interaktif
python gem_visibility_auditor.py --models anthropic gemini openai --runs 3
python gem_visibility_auditor.py --models anthropic:claude-opus-5-5 gemini:gemini-flash-latest groq ollama:llama3.1
python gem_visibility_auditor.py --analyze gem_audit_output/audit_X/responses.csv   # analisis ulang tanpa API
python gem_visibility_auditor.py --resume gem_audit_output/audit_X                  # lanjutkan audit yang terputus
```

Opsi penting: `--langs id en`, `--runs N` (LLM tidak deterministik, ulangi untuk hasil stabil), `--max-questions N`,
`--workers N`, `--config file.json`, `--base-url ollama=http://host:11434/v1`, `--claude-effort low|medium|high`,
`--zip`, `--open`. Lihat `python gem_visibility_auditor.py --help`.

## 4. Dashboard Streamlit

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Tiga sumber data: **Jalankan audit baru** (pilih model, kunci, bahasa, jumlah topik, dengan progress bar),
**Unggah hasil** (`responses.csv` atau `dashboard_data.json`), dan **Contoh (demo)**. Setelah data ada: KPI,
insight otomatis, pilihan destinasi fokus dan pembanding, tab share of voice, per bahasa, per model, per kategori,
penjelajah jawaban dengan pencarian dan sorotan, serta unduhan (CSV aman + paket `.zip`).

**Deploy ke Streamlit Community Cloud:** share.streamlit.io, *New app*, pilih repo ini, file utama
`streamlit_app.py`. Kunci API opsional diisi di *Settings > Secrets*:

```toml
ANTHROPIC_API_KEY = "..."
GEMINI_API_KEY = "..."
```

Perhatian: kunci di Secrets dipakai oleh siapa pun yang membuka aplikasi. Untuk aplikasi publik, kosongkan Secrets
(pengguna menempel kunci sendiri) atau batasi akses aplikasi di pengaturan Streamlit Cloud.

## 5. Aplikasi web (GitHub Pages)

Folder `docs/` adalah aplikasi web statis (tanpa server, tanpa build), dideploy otomatis oleh
`.github/workflows/pages.yml` ke https://samuelhtampubolon.github.io/GEM-Visibility-Auditor/. Bila halaman belum
aktif, buka *Settings > Pages* dan pilih **Source: GitHub Actions** (sekali saja), lalu jalankan ulang workflow.

Tata letak aplikasi: panel kontrol (Audit baru / Impor / Demo, pilihan model dan kunci, bahasa, jumlah topik,
pengulangan, estimasi jumlah permintaan) dan area kerja (progres audit langsung per model, KPI, head-to-head,
insight otomatis, tab Peringkat / Bahasa / Model / Kategori / Jawaban, ekspor CSV/JSON/PDF). Destinasi fokus dan
pembanding bisa diganti kapan saja. Tema terang/gelap, responsif di ponsel.

Provider dari browser: Claude, Gemini, ChatGPT, OpenRouter, Groq, DeepSeek, Mistral, dan Ollama lokal (sebagian
provider bisa memblokir akses browser lewat CORS; gunakan CLI/Colab bila demikian). Logika penghitungan di
`docs/app.js` adalah cermin `gem_visibility_auditor.py`, dan kesamaannya (termasuk insight) diuji otomatis.

Lokal: `python -m http.server -d docs 8000` lalu buka http://localhost:8000.

---

## Provider dan kunci API

| Provider | Kunci (env / Colab Secret / .env) | Model bawaan |
|---|---|---|
| `anthropic` (Claude) | `ANTHROPIC_API_KEY` | `claude-opus-5-5` |
| `gemini` (Google) | `GEMINI_API_KEY` atau `GOOGLE_API_KEY` | `gemini-flash-latest` |
| `openai` (ChatGPT) | `OPENAI_API_KEY` | `gpt-5-mini` |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `openrouter` | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct` |
| `mistral` | `MISTRAL_API_KEY` | `mistral-small-latest` |
| `ollama` (lokal) | tidak perlu | `llama3.1` |
| `demo` | tidak perlu | `simulasi-a`, `simulasi-b` (data **simulasi**, bukan LLM) |

Model lain cukup ditulis `provider:model`, misalnya `gemini:gemini-2.5-pro` atau `openai:gpt-4o`.
Catatan Claude: permintaan memakai `anthropic-version: 2026-10-21`, effort `low` (hemat biaya, bisa diubah dengan
`--claude-effort`), dan server-side fallback bawaan untuk model yang mendukung (`--no-claude-fallback` untuk mematikan).
Mode demo hanya untuk menguji alur; laporan, dashboard, dan grafik selalu memberi label **SIMULASI** pada data demo.

## Pertanyaan dan destinasi

15 topik x 2 bahasa = 30 pertanyaan per model: umum, itinerary 7 hari, bulan madu, keluarga, hemat/backpacker, alam,
budaya, danau, hidden gem, bahari/diving, petualangan, ekowisata, kuliner, tinggal lama/digital nomad, tren tahun ini.
Pertanyaan sengaja tidak menyebut nama destinasi agar jawaban mencerminkan "suara" alami AI.
Lihat semua: `python gem_visibility_auditor.py --list-questions`.

11 destinasi dengan alias: **Danau Toba** (fokus: danau toba, lake toba, toba, samosir, parapat, balige),
**Bali** dan **Labuan Bajo** (kompetitor utama, termasuk ubud, komodo, dll.), Raja Ampat, Yogyakarta & Borobudur,
Lombok & Mandalika, Bromo Tengger Semeru, Likupang & Bunaken, Wakatobi, Belitung, Kelimutu.

**Kustomisasi:** `python gem_visibility_auditor.py --export-config config.json`, ubah `focus`, `competitors`,
`destinations`, atau `questions`, lalu jalankan dengan `--config config.json`.

## Metrik

| Metrik | Definisi |
|---|---|
| Share of AI voice (SOV) | sebutan destinasi / total sebutan semua destinasi x 100% |
| Mention rate | % jawaban yang menyebut destinasi minimal sekali |
| Rata-rata urutan pertama | posisi destinasi saat pertama disebut dalam jawaban (1 = paling awal) |
| Rasio fokus per 100 | untuk setiap 100 sebutan Bali/Labuan Bajo, berapa kali Danau Toba disebut |

Penghitungan memakai regex batas kata tanpa membedakan huruf besar/kecil, alias terpanjang lebih dulu
("Danau Toba" dihitung satu kali, bukan dua), toleran spasi/tanda hubung ("Gili-Trawangan"), dan tidak salah tangkap
kata lain ("Balige" adalah Toba, bukan Bali; "tobacco" bukan Toba).

## File hasil

Setiap audit membuat folder `gem_audit_output/audit_<waktu>/`:

| File | Isi |
|---|---|
| `responses.csv` | semua pertanyaan, jawaban mentah, status/error, latensi, token |
| `mentions.csv` | satu baris per jawaban x destinasi: jumlah sebutan, disebut/tidak, urutan |
| `summary.csv` | SOV, mention rate, urutan rata-rata per destinasi |
| `sov_by_language.csv`, `sov_by_model.csv`, `sov_by_category.csv` | SOV per bahasa, model, kategori |
| `share_of_voice.png`, `sov_by_language.png`, `sov_by_model.png`, `mention_rate.png` | grafik Matplotlib |
| `report.html` | laporan mandiri (grafik tertanam, tabel, contoh jawaban dengan sorotan) |
| `dashboard_data.json` | untuk diunggah ke dashboard web/Streamlit |
| `responses.jsonl` | checkpoint per jawaban (untuk `--resume`) |

## Pengujian dan bukti eksekusi

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -v                    # seluruh tes (fungsi, UI, keamanan)
bash scripts/clean_env_test.sh         # uji di lingkungan bersih + build .exe
```

Yang diuji end-to-end:

* **Jalur HTTP API sungguhan** ke server tiruan yang meniru format wire Claude (`/v1/messages`), Gemini
  (`:generateContent`) dan OpenAI (`/chat/completions`): header (`x-api-key`, `anthropic-version`, `x-goog-api-key`,
  `Bearer`), body, retry 429, error 401, refusal, fallback, part "thought" Gemini diabaikan.
* **CLI** sebagai proses terpisah: 90 permintaan ke 3 provider, mode demo, `--analyze`, `--resume`, kode keluar.
* **Google Colab**: seluruh isi file dijalankan dalam **satu sel** notebook Jupyter (nbclient), grafik tampil inline;
  notebook `GEM_Visibility_Auditor_Colab.ipynb` dicek identik dengan file .py dan ikut dijalankan.
* **Streamlit**: AppTest untuk demo, audit baru, validasi kunci; plus server `streamlit run` sungguhan + screenshot.
* **Aplikasi web**: Chromium (Playwright): layar awal, demo, impor CSV, audit di browser dengan API yang di-mock,
  ganti fokus, kesamaan angka dan insight dengan Python, ekspor, tema, tata letak ponsel.
* **Keamanan**: payload XSS dari file impor tidak dieksekusi, CSP memblokir host asing, kunci tidak bocor ke
  state/storage/ekspor/pesan error, redirect ditolak, kunci tidak dikirim lewat HTTP tanpa enkripsi, CSV formula
  injection dinetralkan, konfigurasi tidak tepercaya ditolak, opsi `--key` dihapus.
* **.exe**: build PyInstaller `--onefile` lalu smoke test (Linux di skrip bersih, Windows di GitHub Actions).

Bukti eksekusi tersimpan di [`evidence/`](evidence/): log uji lingkungan bersih dan screenshot dashboard.
CI: `.github/workflows/tests.yml` (Ubuntu Python 3.10/3.12 + Windows), `build-exe.yml` (build + smoke test + Release),
`pages.yml` (deploy GitHub Pages).

## Keamanan

Ringkasan (detail di [`SECURITY.md`](SECURITY.md)):

* Kunci API hanya dari environment variable, `.env`, Colab Secrets, Streamlit Secrets, atau input tersembunyi;
  tidak pernah dari argumen CLI, tidak ditulis ke file hasil atau log, dan disensor dari pesan error.
* Permintaan API tidak mengikuti redirect (header kunci tidak bisa terbawa ke host lain) dan kunci tidak pernah dikirim
  lewat HTTP tanpa enkripsi kecuali ke `localhost`.
* Aplikasi web: Content Security Policy ketat (`default-src 'none'`, hanya endpoint resmi provider), tanpa
  `innerHTML` untuk data, tanpa penyimpanan kunci, persetujuan eksplisit sebelum kunci dikirim dari browser.
* CSV hasil aman dibuka di Excel/Sheets; laporan HTML memakai CSP tanpa skrip.
* CI: action di-pin ke SHA commit, izin token minimum, rilis tidak bisa ditimpa, checksum SHA-256, Dependabot.

## Keterbatasan

* Jawaban LLM berubah antar-panggilan; pakai `--runs 3` atau lebih untuk angka yang stabil.
* Penghitungan berbasis alias: sebutan negatif tetap dihitung sebagai sebutan. Tambahkan alias sesuai kebutuhan.
* Biaya API ditanggung akun Anda; 30 pertanyaan x jumlah model x `--runs`.

## Struktur repo

```
gem_visibility_auditor.py   # program utama satu file (CLI, wizard .exe, Colab, modul)
streamlit_app.py            # dashboard Streamlit
dashboard_launcher.py       # peluncur dashboard untuk build .exe
docs/                       # dashboard web GitHub Pages (index.html, app.js, style.css, data/)
tests/                      # pytest end-to-end + server API tiruan
scripts/clean_env_test.sh   # uji lingkungan bersih
scripts/build_colab_notebook.py  # bangun ulang notebook Colab dari file .py
GEM_Visibility_Auditor_Colab.ipynb  # notebook Colab satu sel (Open in Colab)
evidence/                   # log dan screenshot bukti eksekusi
SECURITY.md                 # kebijakan dan catatan keamanan
.github/workflows/          # CI tes, build .exe + Release, deploy Pages
```
