# Bukti eksekusi

Semua file di folder ini dihasilkan oleh program dan tes, bukan dibuat manual.

| File | Asal |
|---|---|
| `clean_env_test_log.txt` | `bash scripts/clean_env_test.sh`: checkout bersih dari commit (git archive), virtualenv baru, `pip install -r requirements-dev.txt`, CLI demo, seluruh pytest (fungsi, UI, keamanan), server `streamlit run` sungguhan, build PyInstaller `--onefile` dan smoke test biner |
| `live_endpoint_check.txt` | CLI memanggil endpoint asli `api.anthropic.com` dan `generativelanguage.googleapis.com` dengan kunci sengaja tidak valid (lewat environment variable); kedua server menjawab 401/400 dan pesannya terbaca |
| `web_01_start.png` | aplikasi web: layar awal (panel kontrol + aksi) |
| `web_02_dashboard.png` | dashboard hasil demo: KPI, head-to-head, insight, peringkat |
| `web_03_answers.png` | penjelajah jawaban dengan sorotan sebutan |
| `web_04_consent.png` | dialog persetujuan sebelum kunci dikirim dari browser |
| `web_05_live_result.png` | hasil audit langsung dari browser (respons API di-mock) |
| `web_06_mobile_start.png`, `web_07_mobile_panel.png`, `web_08_mobile_dashboard.png` | tampilan ponsel (375 px) |
| `streamlit_01_start.png`, `streamlit_02_dashboard.png` | dashboard Streamlit yang dilayani `streamlit run` di lingkungan bersih |

Catatan jujur: lingkungan uji tidak memiliki kunci API asli, sehingga jawaban sukses dari LLM diuji lewat server
tiruan yang meniru format wire resmi Claude, Gemini, dan OpenAI (`tests/mock_llm_server.py`). Data contoh berasal
dari mode demo dan selalu diberi label simulasi. Build .exe Windows dan smoke test-nya berjalan di GitHub Actions
(`.github/workflows/build-exe.yml`).
