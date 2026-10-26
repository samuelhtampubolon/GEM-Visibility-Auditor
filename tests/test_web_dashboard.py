"""Uji dashboard web (docs/, GitHub Pages) di Chromium sungguhan lewat Playwright."""

import functools
import glob
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

import gem_visibility_auditor as gva

sync_api = pytest.importorskip("playwright.sync_api")


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


@pytest.fixture()
def page(browser, site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.goto(site)
    pg.wait_for_selector("body[data-ready='1']", timeout=15000)
    yield pg
    ctx.close()


def _evidence(pg, name):
    d = os.environ.get("GEM_EVIDENCE_DIR")
    if d:
        os.makedirs(d, exist_ok=True)
        pg.screenshot(path=os.path.join(d, name), full_page=False)


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


def test_sample_loads_and_matches_python(page, root):
    assert not page.errors, page.errors
    data = json.loads((root / "docs/data/demo_results.json").read_text(encoding="utf-8"))
    _assert_same(_py_summary(data["responses"], data["config"]), _js_summary(page))
    assert page.locator("#sim-banner").is_visible()
    hero = page.locator(".tile.hero .val").inner_text()
    py = gva.analyze(gva.records_to_df(data["responses"]), data["config"])["headline"]
    assert hero == f"{py['focus_sov_pct']:.1f}%"
    assert page.locator("#chart-sov .bar-row").count() == 11
    assert page.locator("#heat-model td.cell").count() == 11 * 2
    _evidence(page, "web_dashboard_desktop.png")


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
        py = {k: v[0] for k, v in gva.scan_text(t, m).items()}
        assert py == j, t


def test_upload_csv_from_cli_matches_python(page, root, tmp_path, mock_server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    cfg = gva.load_config()
    recs = gva.run_audit([("anthropic", "claude-opus-5-5"), ("demo", "simulasi-b")], cfg, ["id", "en"],
                         max_questions=5, opts={"base_urls": {"anthropic": mock_server.base}}, workers=2)
    df = gva.records_to_df(recs)
    path = tmp_path / "responses.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")  # jawaban multi-baris, koma, tanda kutip
    page.locator("[data-src=upload]").click()
    page.set_input_files("#file-input", str(path))
    page.wait_for_function("window.__gem.state.source.includes('responses.csv')")
    assert not page.errors, page.errors
    _assert_same(_py_summary(recs, cfg), _js_summary(page))
    assert page.locator("#meta-line").inner_text().startswith("20 jawaban berhasil")


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
    page.locator("[data-src=run]").click()
    page.fill(".prov[data-p=anthropic] .p-key", "sk-ant-browser")
    page.fill(".prov[data-p=gemini] .p-key", "g-browser")
    page.fill("#run-maxq", "2")
    page.click("#run-btn")
    page.wait_for_function("window.__gem.state.source.startsWith('audit di browser')", timeout=20000)
    assert not page.errors, page.errors
    assert len(calls) == 2 * 2 * 2
    a = next(c for c in calls if c[0] == "anthropic")
    assert a[1]["x-api-key"] == "sk-ant-browser" and a[1]["anthropic-version"] == "2026-10-21"
    assert a[1]["anthropic-dangerous-direct-browser-access"] == "true"
    assert a[2]["model"] == "claude-opus-5-5" and "temperature" not in a[2]
    g = next(c for c in calls if c[0] == "gemini")
    assert g[1]["x-goog-api-key"] == "g-browser"
    recs = page.evaluate("window.__gem.state.records")
    assert len(recs) == 8 and {r["status"] for r in recs} == {"ok"}
    assert page.locator("#sim-banner").is_hidden()
    assert page.locator(".tile.hero .val").inner_text() == "20.0%"  # Toba 4 dari 20 sebutan
    _evidence(page, "web_dashboard_run_in_browser.png")


def test_mobile_layout_no_horizontal_scroll(browser, site):
    ctx = browser.new_context(viewport={"width": 375, "height": 800})
    pg = ctx.new_page()
    pg.goto(site)
    pg.wait_for_selector("body[data-ready='1']")
    assert pg.evaluate("document.documentElement.scrollWidth") <= 375
    _evidence(pg, "web_dashboard_mobile.png")
    ctx.close()
