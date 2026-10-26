#!/usr/bin/env bash
# Uji end-to-end di lingkungan bersih: hanya file yang sudah di-commit (git archive),
# virtualenv baru, dependensi dari requirements, lalu:
#   1) CLI mode demo, 2) seluruh pytest (API tiruan, Colab/notebook, Streamlit, web),
#   3) server Streamlit sungguhan + screenshot, 4) build .exe PyInstaller + smoke test.
# Pakai: bash scripts/clean_env_test.sh [file_log]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${1:-$REPO/evidence/clean_env_test_log.txt}"
EVID="$(dirname "$LOG")"
WORK="$(mktemp -d)"
mkdir -p "$EVID" "$WORK/src"
PY="${PYTHON:-python3}"

run() {
  echo
  echo "## Bersih: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "## Sistem: $(uname -srm), $($PY --version)"
  echo "## Commit: $(git -C "$REPO" rev-parse HEAD)"
  echo "## Folder kerja: $WORK"
  git -C "$REPO" archive HEAD | tar -x -C "$WORK/src"
  cd "$WORK/src"
  echo "## Isi checkout bersih:"; ls -la

  echo; echo "## [1/4] virtualenv baru + pip install -r requirements-dev.txt"
  $PY -m venv "$WORK/venv"
  # shellcheck disable=SC1091
  . "$WORK/venv/bin/activate"
  python -m pip install -q --upgrade pip
  pip install -q -r requirements-dev.txt
  pip freeze | grep -iE "^(pandas|matplotlib|requests|streamlit|pytest|nbclient|ipykernel|playwright|pyinstaller)=="

  echo; echo "## [2/4] CLI mode demo"
  python gem_visibility_auditor.py --demo --out "$WORK/demo_out" --zip
  ls -la "$WORK/demo_out"

  echo; echo "## [3/4] pytest lengkap"
  if [ -z "${PLAYWRIGHT_CHROMIUM_EXECUTABLE:-}" ]; then
    CH="$(ls -d /opt/pw-browsers/chromium-*/chrome-linux*/chrome 2>/dev/null | head -n1 || true)"
    if [ -n "$CH" ]; then export PLAYWRIGHT_CHROMIUM_EXECUTABLE="$CH"; else python -m playwright install chromium; fi
  fi
  GEM_EVIDENCE_DIR="$EVID" PYTHONIOENCODING=utf-8 python -m pytest -v -p no:cacheprovider

  echo; echo "## [3b/4] server Streamlit sungguhan (streamlit run) + screenshot"
  streamlit run streamlit_app.py --server.headless true --server.port 8597 > "$WORK/streamlit.log" 2>&1 &
  ST_PID=$!
  for _ in $(seq 1 60); do curl -sf http://localhost:8597/_stcore/health >/dev/null && break; sleep 1; done
  echo "health: $(curl -sf http://localhost:8597/_stcore/health)"
  EVID="$EVID" python - <<'PYEOF'
import os
from playwright.sync_api import sync_playwright
exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1300, "height": 1000})
    pg.goto("http://localhost:8597/")
    pg.wait_for_selector("text=SOV Danau Toba", timeout=60000)
    pg.wait_for_timeout(2500)
    errs = pg.locator('[data-testid="stException"]').count()
    pg.screenshot(path=os.path.join(os.environ["EVID"], "streamlit_dashboard.png"))
    print("Streamlit dirender, metrik:", pg.locator('[data-testid="stMetricLabel"]').all_inner_texts(), "exceptions:", errs)
    assert errs == 0
    b.close()
PYEOF
  kill "$ST_PID" || true
  deactivate

  echo; echo "## [4/4] build .exe PyInstaller (venv terpisah, dependensi inti saja)"
  $PY -m venv "$WORK/venv-exe"
  # shellcheck disable=SC1091
  . "$WORK/venv-exe/bin/activate"
  python -m pip install -q --upgrade pip
  pip install -q pandas matplotlib requests pyinstaller pytest
  pyinstaller --onefile --name GEM-Visibility-Auditor gem_visibility_auditor.py > "$WORK/pyinstaller.log" 2>&1
  tail -n 2 "$WORK/pyinstaller.log"
  ls -la dist/
  ./dist/GEM-Visibility-Auditor --version
  GEM_EXE_PATH="$PWD/dist/GEM-Visibility-Auditor" python -m pytest -v -p no:cacheprovider tests/test_exe.py
  deactivate

  echo; echo "## SEMUA LANGKAH LULUS"
}

run 2>&1 | tee "$LOG"
