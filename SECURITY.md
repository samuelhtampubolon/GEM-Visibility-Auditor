# Keamanan

## Melaporkan celah

Jangan membuka issue publik untuk celah keamanan. Gunakan **Security > Report a vulnerability** (GitHub private
vulnerability reporting) di repo ini. Sertakan langkah reproduksi dan dampaknya.

## Kunci API

| Tempat | Perlakuan |
|---|---|
| CLI / .exe | Dari environment variable, file `.env` (di `.gitignore`), atau input tersembunyi (getpass). Tidak ada opsi `--key`, supaya kunci tidak tercatat di riwayat shell atau daftar proses. |
| Google Colab | Dari Colab Secrets atau input tersembunyi. |
| Streamlit | Dari Streamlit Secrets atau kolom password per sesi; tombol "Hapus kunci dari sesi". Kunci di Secrets dipakai semua pengunjung aplikasi, jadi kosongkan untuk aplikasi publik. |
| Aplikasi web | Hanya di memori tab; tidak disimpan ke localStorage/sessionStorage, tidak masuk ekspor, input dikosongkan saat halaman ditutup; dialog persetujuan sebelum dikirim. |

Di semua versi: kunci tidak ditulis ke `responses.csv`, `responses.jsonl`, `dashboard_data.json`, `report.html`, atau
log, dan pola kunci disensor (`[REDACTED]`) dari pesan error.

Rekomendasi: buat kunci khusus untuk audit ini dengan batas biaya (spend limit), dan cabut setelah selesai.

## Jaringan

* Permintaan API memakai `allow_redirects=False` (Python) dan `redirect: "error"` (browser), sehingga header
  `x-api-key`, `x-goog-api-key`, atau `Authorization` tidak bisa terbawa ke host lain lewat redirect.
* Kunci tidak dikirim lewat `http://` kecuali ke `localhost`/`127.0.0.1`/`::1`.
* Browser: `credentials: "omit"`, `referrerPolicy: "no-referrer"`, dan Content Security Policy yang hanya mengizinkan
  endpoint resmi: `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.openai.com`, `openrouter.ai`,
  `api.groq.com`, `api.deepseek.com`, `api.mistral.ai`, serta Ollama di `localhost:11434`.
* Ollama dari browser: izinkan hanya origin aplikasi ini, misalnya
  `OLLAMA_ORIGINS=https://samuelhtampubolon.github.io ollama serve` (jangan `*`).

## Data tidak tepercaya

Jawaban LLM dan file yang diimpor diperlakukan sebagai data tidak tepercaya:

* Aplikasi web membangun DOM dengan `textContent`/`createElement`, tanpa `innerHTML` untuk data; CSP
  `script-src 'self'` tanpa `unsafe-inline`/`unsafe-eval`.
* `report.html` dan Streamlit meng-escape semua teks (`html.escape`); `report.html` memakai CSP tanpa skrip.
* File impor dibatasi 25 MB, kolom disaring, panjang teks dibatasi, dan konfigurasi divalidasi ketat (ID, nama,
  alias, jumlah pertanyaan); konfigurasi tidak valid ditolak.
* Ekspor CSV menetralkan formula injection (sel diawali `=`, `+`, `-`, `@` diberi awalan apostrof) dan dibaca
  kembali dengan benar oleh program ini.

## Rantai pasok dan rilis

* Semua GitHub Action di-pin ke SHA commit; Dependabot memperbarui action dan dependensi pip tiap minggu.
* Token workflow bawaan hanya `contents: read`; hanya job rilis yang mendapat `contents: write`.
* Rilis dibuat dengan `gh` CLI bawaan runner (tanpa action pihak ketiga), tidak pernah menimpa rilis yang sudah ada,
  dan menyertakan `SHA256SUMS.txt` yang diverifikasi sebelum diunggah.
* Biner .exe belum ditandatangani kode (code signing); verifikasi dengan SHA-256.
