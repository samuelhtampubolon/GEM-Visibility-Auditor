"""Uji logika penghitungan sebutan dan analisis share of voice."""

import pandas as pd
import pytest

import gem_visibility_auditor as gva


@pytest.fixture()
def cfg():
    return gva.load_config()


@pytest.fixture()
def matchers(cfg):
    return gva.build_matchers(cfg["destinations"])


def test_alias_counting_longest_first(matchers):
    hits = gva.scan_text("Danau Toba, Lake Toba, dan Pulau Samosir. Toba!", matchers)
    assert hits["danau_toba"][0] == 4  # 'danau toba' dihitung sekali, bukan dua
    assert hits["bali"][0] == 0


def test_word_boundaries_and_case(matchers):
    text = "Balige ada di tepi danau. KOMODO dan pulau Padar. Balinese food di Ubud."
    hits = gva.scan_text(text, matchers)
    assert hits["danau_toba"][0] == 1      # Balige -> Toba, bukan Bali
    assert hits["bali"][0] == 2            # balinese + ubud
    assert hits["labuan_bajo"][0] == 2     # komodo + pulau padar


def test_hyphen_and_whitespace_variants(matchers):
    hits = gva.scan_text("Gili-Trawangan,  Raja\nAmpat, Labuan   Bajo", matchers)
    assert hits["lombok"][0] == 1
    assert hits["raja_ampat"][0] == 1
    assert hits["labuan_bajo"][0] == 1


def test_no_partial_word_match(matchers):
    hits = gva.scan_text("Kabalian, tobacco, jogjakartanese, manadonese", matchers)
    assert all(v[0] == 0 for v in hits.values())


def test_first_position(matchers):
    hits = gva.scan_text("Bali dulu, lalu Danau Toba.", matchers)
    assert hits["bali"][1] < hits["danau_toba"][1]


def test_find_spans_for_highlight(cfg, matchers):
    text = "Lake Toba and Bali."
    spans = gva.find_spans(text, matchers)
    assert [(text[s:e], d) for s, e, d in spans] == [("Lake Toba", "danau_toba"), ("Bali", "bali")]
    html = gva._highlight_html(text, matchers, cfg)
    assert '<mark class="focus"' in html and '<mark class="competitor"' in html
    assert "Lake Toba" in html  # huruf asli tetap


def _rec(rid, model, lang, text, status="ok"):
    return {"response_id": rid, "provider": "x", "model": model, "model_label": f"x:{model}",
            "question_id": "Q01", "category": "Umum", "language": lang, "run": 1, "prompt": "p",
            "response": text, "status": status, "error": "" if status == "ok" else "boom", "simulated": False}


def test_analyze_share_of_voice(cfg):
    df = gva.records_to_df([
        _rec("a", "m1", "id", "Bali, Bali, Danau Toba"),
        _rec("b", "m1", "en", "Lake Toba then Labuan Bajo"),
        _rec("c", "m2", "id", "Raja Ampat"),
        _rec("d", "m2", "en", "", status="error"),
    ])
    res = gva.analyze(df, cfg)
    s = res["summary"].set_index("destination_id")
    total = 2 + 2 + 1 + 1
    assert s.loc["danau_toba", "mentions"] == 2
    assert s.loc["danau_toba", "share_of_voice_pct"] == round(2 / total * 100, 2)
    assert s.loc["bali", "mention_rate_pct"] == round(1 / 3 * 100, 2)  # 3 jawaban ok
    assert s.loc["danau_toba", "avg_first_rank"] == 1.5  # rank 2 di 'a', rank 1 di 'b'
    assert abs(res["summary"]["share_of_voice_pct"].sum() - 100) < 0.05
    h = res["headline"]
    assert h["responses_ok"] == 3 and h["responses_error"] == 1
    bali = next(c for c in h["competitors"] if c["id"] == "bali")
    assert bali["focus_per_100"] == 100.0  # 2 sebutan Toba vs 2 sebutan Bali
    bl = res["by_language"]
    assert set(bl["language"]) == {"id", "en"}
    for _, sub in bl.groupby("language"):
        assert abs(sub["share_of_voice_pct"].sum() - 100) < 0.05
    assert set(res["by_model"]["model_label"]) == {"x:m1", "x:m2"}


def test_analyze_all_errors(cfg):
    df = gva.records_to_df([_rec("a", "m1", "id", "", status="error")])
    res = gva.analyze(df, cfg)
    assert res["headline"]["responses_ok"] == 0
    assert (res["summary"]["share_of_voice_pct"] == 0).all()


def test_parse_model_specs():
    assert gva.parse_model_specs(["anthropic", "gemini:gemini-2.5-pro", "openai,groq"]) == [
        ("anthropic", "claude-opus-5-5"), ("gemini", "gemini-2.5-pro"),
        ("openai", "gpt-5-mini"), ("groq", "llama-3.3-70b-versatile")]
    with pytest.raises(ValueError):
        gva.parse_model_specs(["tidakada"])


def test_build_tasks_counts(cfg):
    tasks = gva.build_tasks([("demo", "a"), ("demo", "b")], cfg, ["id", "en"], runs=2)
    assert len(tasks) == 2 * 15 * 2 * 2
    assert len({t["response_id"] for t in tasks}) == len(tasks)
    assert len(cfg["questions"]) * 2 == 30  # 30 pertanyaan wisata per model


def test_config_override(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"focus": "bali", "competitors": ["danau_toba"]}', encoding="utf-8")
    cfg = gva.load_config(str(p))
    assert cfg["focus"] == "bali"
    p.write_text('{"focus": "tidakada"}', encoding="utf-8")
    with pytest.raises(ValueError):
        gva.load_config(str(p))


def test_csv_roundtrip(cfg, tmp_path):
    recs = gva.run_audit([("demo", "simulasi-a")], cfg, ["id", "en"], max_questions=3, workers=1)
    df = gva.records_to_df(recs)
    path = tmp_path / "responses.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    back = gva.read_responses_csv(str(path))
    a = gva.analyze(df, cfg)["summary"]
    b = gva.analyze(back, cfg)["summary"]
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_dotenv_loading(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("# komentar\nexport GEMINI_API_KEY='abc123'\n", encoding="utf-8")
    gva.load_dotenv_files()
    assert gva.resolve_key("gemini") == "abc123"
    monkeypatch.delenv("GEMINI_API_KEY")


def test_no_em_dash_in_sources(root):
    for p in list(root.glob("*.py")) + list(root.glob("*.md")) + list((root / "docs").rglob("*.*")) \
            + list((root / "tests").glob("*.py")) + list((root / ".github").rglob("*.yml")):
        if p.suffix in {".png", ".ico"}:
            continue
        assert chr(0x2014) not in p.read_text(encoding="utf-8"), f"em dash di {p}"


def test_csv_formula_injection_neutralized(cfg, tmp_path):
    recs = [_rec("a", "m1", "id", "=HYPERLINK(\"http://evil\",\"klik\") Bali"),
            _rec("b", "m1", "en", "- Lake Toba\n- Bali"), _rec("c", "m1", "en", "@SUM(1) Komodo")]
    df = gva.records_to_df(recs)
    raw = gva.to_csv_bytes(df).decode("utf-8-sig")
    assert "\n=" not in raw and ",=" not in raw and "'=HYPERLINK" in raw and "'@SUM" in raw
    path = tmp_path / "r.csv"
    path.write_bytes(gva.to_csv_bytes(df))
    back = gva.read_responses_csv(str(path))
    assert list(back["response"]) == list(df["response"])  # isi asli kembali utuh


def test_untrusted_config_rejected(tmp_path):
    bad = [
        '{"destinations": [{"id": "x<script>", "name": "X", "aliases": ["x"]}], "focus": "x<script>"}',
        '{"destinations": "bukan daftar"}',
        '{"destinations": [{"id": "a", "name": "A", "aliases": [1, 2]}], "focus": "a", "competitors": []}',
        '{"questions": [{"qid": "Q", "text": {"id": 5}}]}',
    ]
    for i, txt in enumerate(bad):
        p = tmp_path / f"c{i}.json"
        p.write_text(txt, encoding="utf-8")
        with pytest.raises(ValueError):
            gva.load_config(str(p))


def test_insights(cfg):
    recs = gva.run_audit([("demo", "simulasi-a"), ("demo", "simulasi-b")], cfg, ["id", "en"], workers=1)
    res = gva.analyze(gva.records_to_df(recs), cfg)
    ins = gva.build_insights(res)
    assert len(ins) >= 6 and ins[0].startswith("Danau Toba berada di peringkat")
    assert any("Setiap 100 sebutan Bali" in t for t in ins)


def test_report_csp_uses_style_hash_not_unsafe(cfg, tmp_path):
    import base64
    import hashlib
    recs = gva.run_audit([("demo", "simulasi-a")], cfg, ["id"], max_questions=2, workers=1)
    df = gva.records_to_df(recs)
    paths = gva.export_outputs(df, gva.analyze(df, cfg), cfg, tmp_path / "out")
    html_text = paths["report.html"].read_text(encoding="utf-8")
    assert "unsafe" not in html_text.split("</head>")[0]
    css = html_text.split("<style>", 1)[1].split("</style>", 1)[0]
    digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
    assert f"style-src 'sha256-{digest}'" in html_text
    assert "<script" not in html_text.lower()
