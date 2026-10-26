# Bukti eksekusi

Semua file di folder ini dihasilkan oleh program dan tes, bukan dibuat manual.

| File | Asal |
|---|---|
| `clean_env_test_log.txt` | `bash scripts/clean_env_test.sh`: checkout bersih dari commit (git archive), virtualenv baru, `pip install -r requirements-dev.txt`, CLI demo, 46 tes pytest, server `streamlit run` sungguhan, build PyInstaller `--onefile` dan smoke test biner |
| `live_endpoint_check.txt` | CLI memanggil endpoint asli `api.anthropic.com` dan `generativelanguage.googleapis.com` dengan kunci sengaja tidak valid; kedua server menjawab 401/400 dan pesannya terbaca, membuktikan URL, header, dan penanganan error |
| `web_dashboard_desktop.png` | Playwright + Chromium, dashboard GitHub Pages memuat contoh demo |
| `web_dashboard_run_in_browser.png` | audit langsung dari browser (Claude + Gemini, respons API di-mock) |
| `web_dashboard_mobile.png` | tata letak lebar 375 px tanpa scroll horizontal |
| `streamlit_dashboard.png` | dashboard Streamlit yang dilayani `streamlit run` di lingkungan bersih |

Catatan jujur: lingkungan uji tidak memiliki kunci API asli, sehingga jawaban sukses dari LLM diuji lewat server
tiruan yang meniru format wire resmi Claude, Gemini, dan OpenAI (`tests/mock_llm_server.py`). Data contoh di
dashboard berasal dari mode demo dan selalu diberi label SIMULASI. Build .exe Windows dan smoke test-nya berjalan
di GitHub Actions (`.github/workflows/build-exe.yml`).
