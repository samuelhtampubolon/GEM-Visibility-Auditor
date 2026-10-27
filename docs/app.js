/* GEM Visibility Auditor: aplikasi web (GitHub Pages).
 *
 * Keamanan:
 * - DOM dibangun dengan createElement/textContent; data dari LLM atau file impor tidak pernah lewat innerHTML.
 * - Kunci API hanya dibaca dari input saat audit dimulai, tidak disimpan ke storage, tidak masuk ekspor,
 *   disensor dari pesan error, dan input dikosongkan saat halaman ditutup.
 * - fetch: redirect "error", credentials "omit", no-referrer; CSP di index.html membatasi host tujuan.
 * - File impor divalidasi (ukuran, kolom, panjang teks, konfigurasi); ekspor CSV menetralkan formula.
 *
 * Logika analisis adalah cermin gem_visibility_auditor.py (alias, regex batas kata, share of voice,
 * mention rate, urutan pertama, insight) dan kesamaannya diuji otomatis. */
"use strict";
(function () {
  const ANTHROPIC_VERSION = "2026-10-21";
  const CLAUDE_FALLBACK_MODELS = new Set(["claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"]);
  const RESPONSE_COLUMNS = [
    "response_id", "timestamp", "provider", "model", "model_label", "question_id", "category",
    "language", "run", "prompt", "response", "status", "error", "latency_s",
    "input_tokens", "output_tokens", "stop_reason", "simulated",
  ];
  const LANG_LABELS = { id: "Bahasa Indonesia", en: "English" };
  const LANG_SHORT = { id: "Indonesia", en: "Inggris" };
  const HEAT = ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];
  const LIMITS = { fileBytes: 25 * 1024 * 1024, records: 20000, text: 100000, field: 2000 };
  const PAGE = 20;
  const PROVIDERS = {
    anthropic: { name: "Claude", vendor: "Anthropic", kind: "anthropic", base: "https://api.anthropic.com", model: "claude-opus-5-5",
      models: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], key: true, keyUrl: "https://console.anthropic.com/settings/keys" },
    gemini: { name: "Gemini", vendor: "Google", kind: "gemini", base: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-flash-latest",
      models: ["gemini-flash-latest", "gemini-2.5-pro", "gemini-2.5-flash"], key: true, keyUrl: "https://aistudio.google.com/apikey" },
    openai: { name: "ChatGPT", vendor: "OpenAI", kind: "openai", base: "https://api.openai.com/v1", model: "gpt-5-mini",
      models: ["gpt-5-mini", "gpt-5", "gpt-4o"], key: true, keyUrl: "https://platform.openai.com/api-keys" },
    openrouter: { name: "OpenRouter", vendor: "banyak model", kind: "openai", base: "https://openrouter.ai/api/v1", model: "meta-llama/llama-3.3-70b-instruct",
      models: ["meta-llama/llama-3.3-70b-instruct", "mistralai/mistral-small", "qwen/qwen-2.5-72b-instruct"], key: true, keyUrl: "https://openrouter.ai/keys" },
    groq: { name: "Groq", vendor: "Groq", kind: "openai", base: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile",
      models: ["llama-3.3-70b-versatile"], key: true, keyUrl: "https://console.groq.com/keys" },
    deepseek: { name: "DeepSeek", vendor: "DeepSeek", kind: "openai", base: "https://api.deepseek.com/v1", model: "deepseek-chat",
      models: ["deepseek-chat"], key: true, keyUrl: "https://platform.deepseek.com/api_keys" },
    mistral: { name: "Mistral", vendor: "Mistral AI", kind: "openai", base: "https://api.mistral.ai/v1", model: "mistral-small-latest",
      models: ["mistral-small-latest", "mistral-large-latest"], key: true, keyUrl: "https://console.mistral.ai/api-keys" },
    ollama: { name: "Ollama", vendor: "lokal", kind: "openai", base: "http://localhost:11434/v1", model: "llama3.1",
      models: ["llama3.1", "qwen2.5"], key: false,
      note: "Model di komputer Anda sendiri. Jalankan: OLLAMA_ORIGINS=" + location.origin + " ollama serve" },
  };
  const DEFAULT_ON = ["anthropic", "gemini"];

  const state = {
    defaultConfig: null, config: null, records: [], source: "", kind: "", results: null,
    focus: null, competitors: null, tab: "rank", shown: PAGE, running: false, abort: null,
  };
  const $ = (id) => document.getElementById(id);

  // -------------------------------------------------------------------------
  // DOM helper (tanpa innerHTML untuk data)
  // -------------------------------------------------------------------------
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "style") Object.assign(el.style, v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k === "text") el.textContent = v;
        else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : String(c));
    }
    return el;
  }
  function icon(id) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    const use = document.createElementNS(ns, "use");
    use.setAttribute("href", "#" + id);
    svg.append(use);
    return svg;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function toast(msg, kind) {
    const t = h("div", { class: "toast" + (kind ? " " + kind : ""), role: kind === "error" ? "alert" : "status", text: msg });
    $("toasts").append(t);
    setTimeout(() => t.remove(), kind === "error" ? 7000 : 4000);
  }
  const fx = (v, d) => Number(v).toFixed(d);
  const pct = (v, d = 1) => `${fx(v, d)}%`;

  // -------------------------------------------------------------------------
  // Analisis (cermin Python)
  // -------------------------------------------------------------------------
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function aliasPattern(a) { return a.normalize("NFKC").toLowerCase().trim().split(/\s+/).map(escapeRe).join("[\\s\\-]+"); }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function buildMatchers(dests) {
    return dests.map((d) => {
      const al = Array.from(new Set(d.aliases.filter((a) => a.trim()))).sort((a, b) => (b.length - a.length) || cmp(a, b));
      return { id: d.id, re: new RegExp("(?<![\\p{L}\\p{N}_])(?:" + al.map(aliasPattern).join("|") + ")(?![\\p{L}\\p{N}_])", "giu") };
    });
  }
  function scanText(text, matchers) {
    const norm = String(text || "").normalize("NFKC");
    const out = {};
    for (const m of matchers) {
      const hits = Array.from(norm.matchAll(m.re), (x) => x.index);
      out[m.id] = [hits.length, hits.length ? hits[0] : null];
    }
    return out;
  }
  function findSpans(text, matchers) {
    const norm = String(text || "").normalize("NFKC");
    const spans = [];
    for (const m of matchers) for (const x of norm.matchAll(m.re)) spans.push([x.index, x.index + x[0].length, m.id]);
    spans.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]) || cmp(a[2], b[2]));
    const merged = []; let last = -1;
    for (const s of spans) if (s[0] >= last) { merged.push(s); last = s[1]; }
    return { norm, spans: merged };
  }
  function groupOf(cfg, id) { return id === cfg.focus ? "focus" : cfg.competitors.includes(id) ? "competitor" : "other"; }
  function destName(cfg, id) { const d = cfg.destinations.find((x) => x.id === id); return d ? d.name : id; }
  const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

  function sovTable(rows, n, cfg) {
    const order = {}; cfg.destinations.forEach((d, i) => { order[d.id] = i; });
    const agg = {};
    for (const d of cfg.destinations) agg[d.id] = { mentions: 0, rm: 0, rankSum: 0, rankN: 0 };
    for (const r of rows) {
      const a = agg[r.destination_id];
      a.mentions += r.count;
      if (r.mentioned) { a.rm += 1; a.rankSum += r.first_rank; a.rankN += 1; }
    }
    const total = Object.values(agg).reduce((s, a) => s + a.mentions, 0);
    const t = cfg.destinations.map((d) => {
      const a = agg[d.id];
      return { destination_id: d.id, destination: d.name, group: groupOf(cfg, d.id), mentions: a.mentions, responses_mentioned: a.rm,
        sov: total ? a.mentions / total * 100 : 0, rate: n ? a.rm / n * 100 : 0, avg: a.rankN ? a.rankSum / a.rankN : null };
    });
    t.sort((x, y) => (y.sov - x.sov) || (order[x.destination_id] - order[y.destination_id]));
    return t.map((r, i) => ({
      rank: i + 1, destination_id: r.destination_id, destination: r.destination, group: r.group, mentions: r.mentions,
      responses_mentioned: r.responses_mentioned, share_of_voice_pct: round2(r.sov), mention_rate_pct: round2(r.rate),
      avg_first_rank: r.avg === null ? null : round2(r.avg),
    }));
  }

  function analyze(records, cfg) {
    const ok = records.filter((r) => r.status === "ok");
    const matchers = buildMatchers(cfg.destinations);
    const rows = [];
    for (const r of ok) {
      const hits = scanText(r.response, matchers);
      const ranked = Object.entries(hits).filter(([, v]) => v[0] > 0).map(([d, v]) => [v[1], d]).sort((a, b) => (a[0] - b[0]) || cmp(a[1], b[1]));
      const rankOf = {}; ranked.forEach(([, d], i) => { rankOf[d] = i + 1; });
      for (const d of cfg.destinations) {
        const cnt = hits[d.id][0];
        rows.push({ response_id: r.response_id, model_label: r.model_label, language: r.language, category: r.category,
          question_id: r.question_id, destination_id: d.id, count: cnt, mentioned: cnt > 0, first_rank: rankOf[d.id] || null });
      }
    }
    const summary = sovTable(rows, ok.length, cfg);
    const by = (dim) => {
      const groups = new Map();
      for (const r of rows) { if (!groups.has(r[dim])) groups.set(r[dim], []); groups.get(r[dim]).push(r); }
      const out = [];
      for (const [val, sub] of groups) {
        const n = new Set(sub.map((x) => x.response_id)).size;
        for (const t of sovTable(sub, n, cfg)) out.push(Object.assign({ [dim]: val, responses: n }, t));
      }
      return out;
    };
    const byId = Object.fromEntries(summary.map((s) => [s.destination_id, s]));
    const f = byId[cfg.focus];
    const headline = {
      focus_id: cfg.focus, focus_name: destName(cfg, cfg.focus), focus_sov_pct: f.share_of_voice_pct,
      focus_rank: ok.length ? f.rank : null, focus_mention_rate_pct: f.mention_rate_pct, destinations: cfg.destinations.length,
      responses_ok: ok.length, responses_total: records.length, responses_error: records.length - ok.length,
      models: Array.from(new Set(records.map((r) => r.model_label))).sort(),
      simulated: records.some((r) => r.simulated === true),
      competitors: cfg.competitors.map((c) => {
        const s = byId[c];
        return { id: c, name: destName(cfg, c), sov_pct: s.share_of_voice_pct, mention_rate_pct: s.mention_rate_pct,
          focus_per_100: s.share_of_voice_pct ? Math.round(f.share_of_voice_pct / s.share_of_voice_pct * 1000) / 10 : null };
      }),
    };
    return { mentions: rows, summary, by_language: by("language"), by_model: by("model_label"), by_category: by("category"), headline };
  }

  function buildInsights(res) {
    const hd = res.headline;
    if (!hd.responses_ok) return [];
    const f = hd.focus_name, fid = hd.focus_id, s = res.summary, top = s[0], out = [];
    if (top.destination_id === fid) out.push(`${f} adalah destinasi paling dominan di jawaban AI (${fx(hd.focus_sov_pct, 1)}% share of voice).`);
    else out.push(`${f} berada di peringkat ${hd.focus_rank} dari ${hd.destinations} dengan ${fx(hd.focus_sov_pct, 1)}% share of voice; ${top.destination} memimpin dengan ${fx(top.share_of_voice_pct, 1)}%.`);
    for (const c of hd.competitors) if (c.focus_per_100 !== null) out.push(`Setiap 100 sebutan ${c.name}, ${f} disebut ${fx(c.focus_per_100, 0)} kali.`);
    const frow = s.find((r) => r.destination_id === fid);
    if (frow.responses_mentioned) out.push(`${f} muncul di ${fx(hd.focus_mention_rate_pct, 0)}% jawaban; saat disebut, rata-rata di urutan ke-${fx(frow.avg_first_rank, 1)} di antara destinasi lain.`);
    else out.push(`${f} tidak disebut sama sekali di ${hd.responses_ok} jawaban.`);
    const focusBy = (t, dim) => t.filter((r) => r.destination_id === fid).map((r) => [r[dim], r.share_of_voice_pct]);
    const langs = Object.fromEntries(focusBy(res.by_language, "language"));
    if ("id" in langs && "en" in langs && Math.abs(langs.id - langs.en) >= 0.5) {
      const [hi, lo] = langs.en > langs.id ? ["en", "id"] : ["id", "en"];
      out.push(`${f} lebih kuat di pertanyaan ${LANG_LABELS[hi]} (${fx(langs[hi], 1)}%) dibanding ${LANG_LABELS[lo]} (${fx(langs[lo], 1)}%).`);
    }
    const cats = focusBy(res.by_category, "category").sort((a, b) => b[1] - a[1]);
    if (cats.length >= 2 && cats[0][1] !== cats[cats.length - 1][1]) {
      const best = cats[0], worst = cats[cats.length - 1];
      const zero = cats.filter((c) => c[1] === 0).map((c) => c[0]);
      out.push(`Kategori terkuat untuk ${f}: ${best[0]} (${fx(best[1], 1)}%); terlemah: ${worst[0]} (${fx(worst[1], 1)}%).`);
      if (zero.length) out.push(`Peluang konten: ${f} tidak muncul di ${zero.length} dari ${cats.length} kategori (${zero.slice(0, 5).join(", ")}${zero.length > 5 ? ", ..." : ""}).`);
    }
    const models = focusBy(res.by_model, "model_label").sort((a, b) => b[1] - a[1]);
    if (models.length >= 2) {
      const a = models[0], b = models[models.length - 1];
      out.push(`Model yang paling sering menyebut ${f}: ${a[0]} (${fx(a[1], 1)}%); paling jarang: ${b[0]} (${fx(b[1], 1)}%).`);
    }
    return out;
  }

  // -------------------------------------------------------------------------
  // CSV, validasi impor, sanitasi
  // -------------------------------------------------------------------------
  const FORMULA = /^[=+\-@\t\r]/;
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    const rows = []; let row = [], field = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
      else if (c === '"') q = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== "\r") field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    const head = rows.shift() || [];
    return rows.filter((r) => r.length > 1 || r[0] !== "").map((r) => {
      const o = Object.create(null);
      head.forEach((hname, j) => { o[hname] = r[j] === undefined ? "" : r[j]; });
      return o;
    });
  }
  function csvCell(v) {
    if (v === null || v === undefined) return "";
    let s = String(v);
    if (FORMULA.test(s)) s = "'" + s; // netralkan formula injection (Excel/Sheets)
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function toCSV(rows, cols) {
    return "﻿" + [cols.join(",")].concat(rows.map((r) => cols.map((c) => csvCell(r[c])).join(","))).join("\n") + "\n";
  }
  function cleanStr(v, max) {
    let s = v === null || v === undefined ? "" : String(v);
    if (s.length > 1 && s[0] === "'" && FORMULA.test(s.slice(1))) s = s.slice(1);
    return s.length > max ? s.slice(0, max) : s;
  }
  function sanitizeRecord(r) {
    const o = {};
    for (const c of RESPONSE_COLUMNS) o[c] = cleanStr(r[c], c === "response" ? LIMITS.text : LIMITS.field);
    o.status = o.status === "error" ? "error" : (o.status === "ok" || o.status === "" ? "ok" : "error");
    o.run = parseInt(o.run, 10) || 1;
    for (const c of ["latency_s", "input_tokens", "output_tokens"]) { const n = parseFloat(o[c]); o[c] = Number.isFinite(n) ? n : null; }
    o.simulated = r.simulated === true || String(r.simulated).toLowerCase() === "true";
    o.model_label = o.model_label || `${o.provider}:${o.model}`;
    o.response_id = o.response_id || `${o.model_label}|${o.question_id}|${o.language}|${o.run}`;
    return o;
  }
  function validConfig(c) {
    const str = (v, max) => typeof v === "string" && v.trim().length > 0 && v.length <= max;
    try {
      if (!c || !Array.isArray(c.destinations) || c.destinations.length < 1 || c.destinations.length > 60) return false;
      for (const d of c.destinations) {
        if (!d || !/^[a-z0-9_]{1,40}$/.test(d.id) || !str(d.name, 80)) return false;
        if (!Array.isArray(d.aliases) || !d.aliases.length || d.aliases.length > 40 || !d.aliases.every((a) => str(a, 80))) return false;
      }
      const ids = c.destinations.map((d) => d.id);
      if (new Set(ids).size !== ids.length || !ids.includes(c.focus)) return false;
      if (!Array.isArray(c.competitors) || !c.competitors.every((x) => ids.includes(x))) return false;
      if (!Array.isArray(c.questions) || !c.questions.length || c.questions.length > 200) return false;
      for (const q of c.questions) {
        if (!q || !str(q.qid, 40) || !q.text || typeof q.text !== "object") return false;
        if (!Object.values(q.text).every((t) => str(t, 2000))) return false;
      }
      return true;
    } catch (_) { return false; }
  }
  function pickConfig(c) {
    return {
      focus: c.focus, competitors: c.competitors.slice(),
      destinations: c.destinations.map((d) => ({ id: d.id, name: d.name, aliases: d.aliases.slice() })),
      questions: c.questions.map((q) => ({ qid: q.qid, category: typeof q.category === "string" ? q.category.slice(0, 80) : "", text: Object.assign({}, q.text) })),
    };
  }

  // -------------------------------------------------------------------------
  // Preferensi (bukan rahasia) di localStorage
  // -------------------------------------------------------------------------
  const PREF_KEY = "gem-prefs-v1";
  function loadPrefs() { try { return JSON.parse(localStorage.getItem(PREF_KEY) || "{}") || {}; } catch (_) { return {}; } }
  function savePrefs(p) { try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (_) { /* mode privat */ } }
  let prefs = loadPrefs();
  function storePrefs() {
    const prov = {};
    for (const row of document.querySelectorAll(".prov")) prov[row.dataset.p] = { on: row.querySelector(".p-on").checked, model: row.querySelector(".p-model").value };
    prefs = Object.assign(prefs, { providers: prov, langs: selectedLangs(), maxq: $("run-maxq").value, runs: $("run-runs").value });
    savePrefs(prefs); // sengaja TIDAK menyimpan kunci API
  }

  // -------------------------------------------------------------------------
  // Panel kontrol: provider, pertanyaan, estimasi
  // -------------------------------------------------------------------------
  function buildProviders() {
    const list = clear($("provider-list"));
    for (const [p, info] of Object.entries(PROVIDERS)) {
      const pref = (prefs.providers || {})[p] || {};
      const on = pref.on !== undefined ? !!pref.on : DEFAULT_ON.includes(p);
      const dl = h("datalist", { id: "dl-" + p }, info.models.map((m) => h("option", { value: m })));
      const modelInput = h("input", { type: "text", class: "p-model", value: pref.model || info.model, list: "dl-" + p, spellcheck: "false", autocomplete: "off", "aria-label": `Model ${info.name}` });
      const body = h("div", { class: "prov-body" },
        h("label", null, "Model (pisahkan koma untuk beberapa)", modelInput, dl),
        info.key ? h("label", null, "Kunci API",
          h("div", { class: "key-wrap" },
            h("input", { type: "password", class: "p-key", autocomplete: "off", spellcheck: "false", "data-lpignore": "true",
              placeholder: "tempel kunci API", "aria-label": `Kunci API ${info.name}` }),
            h("button", { type: "button", class: "icon-btn eye", "aria-label": "Tampilkan atau sembunyikan kunci" }, icon("i-eye")))) : null,
        info.key ? h("span", { class: "hint" }, "Buat kunci khusus di ", h("a", { href: info.keyUrl, target: "_blank", rel: "noopener noreferrer", text: new URL(info.keyUrl).host })) : null,
        info.note ? h("span", { class: "hint", text: info.note }) : null);
      const toggle = h("input", { type: "checkbox", class: "p-on", "aria-label": `Aktifkan ${info.name}` });
      toggle.checked = on;
      const status = h("span", { class: "prov-status" });
      const row = h("div", { class: "prov" + (on ? " on" : ""), dataset: { p } },
        h("div", { class: "prov-head" },
          h("span", { class: "switch" }, toggle, h("i")),
          h("span", null, h("span", { class: "prov-name", text: info.name }), " ", h("span", { class: "prov-vendor", text: info.vendor })),
          status),
        body);
      body.hidden = !on;
      row.querySelector(".prov-head").addEventListener("click", (e) => {
        if (e.target === toggle) return;
        toggle.checked = !toggle.checked;
        toggle.dispatchEvent(new Event("change"));
      });
      toggle.addEventListener("change", () => { body.hidden = !toggle.checked; row.classList.toggle("on", toggle.checked); refreshControls(); storePrefs(); });
      modelInput.addEventListener("change", () => { refreshControls(); storePrefs(); });
      const key = row.querySelector(".p-key");
      if (key) {
        key.addEventListener("input", refreshControls);
        row.querySelector(".eye").addEventListener("click", () => { key.type = key.type === "password" ? "text" : "password"; });
      }
      list.append(row);
    }
  }
  function selectedLangs() { return Array.from(document.querySelectorAll("#lang-chips input:checked")).map((i) => i.value); }
  function selectedModels() {
    const out = [];
    for (const row of document.querySelectorAll(".prov")) {
      if (!row.querySelector(".p-on").checked) continue;
      const p = row.dataset.p;
      for (const m of row.querySelector(".p-model").value.split(",").map((x) => x.trim()).filter(Boolean)) out.push({ p, m });
    }
    return out;
  }
  function refreshControls() {
    let ready = 0, active = 0;
    for (const row of document.querySelectorAll(".prov")) {
      const info = PROVIDERS[row.dataset.p], on = row.querySelector(".p-on").checked;
      const key = row.querySelector(".p-key"), st = row.querySelector(".prov-status");
      const has = !info.key || (key && key.value.trim().length > 0);
      if (on) { active++; if (has) ready++; }
      st.className = "prov-status" + (on ? (has ? " ready" : " need") : "");
      st.textContent = on ? (has ? "siap" : "butuh kunci") : "nonaktif";
    }
    $("prov-count").textContent = `${active} aktif`;
    const models = selectedModels(), langs = selectedLangs();
    const maxq = parseInt($("run-maxq").value, 10), runs = Math.max(1, Math.min(5, parseInt($("run-runs").value, 10) || 1));
    $("maxq-out").textContent = String(maxq);
    const n = models.length * maxq * langs.length * runs;
    clear($("estimate")).append(h("b", { text: `${n} permintaan` }), h("span", { class: "muted", text: ` ke ${models.length} model (${maxq} topik x ${langs.length} bahasa x ${runs} ulang)` }));
    $("run-btn").disabled = state.running || !n;
  }
  function buildQuestionList() {
    const ol = clear($("question-list"));
    for (const q of state.defaultConfig.questions) ol.append(h("li", null, h("b", { text: q.category + ": " }), q.text.id || Object.values(q.text)[0]));
    $("run-maxq").max = String(state.defaultConfig.questions.length);
  }

  // -------------------------------------------------------------------------
  // Fokus analisis
  // -------------------------------------------------------------------------
  function effectiveConfig() {
    const c = state.config;
    const ids = c.destinations.map((d) => d.id);
    const focus = ids.includes(state.focus) ? state.focus : c.focus;
    const comps = (state.competitors || c.competitors).filter((x) => ids.includes(x) && x !== focus).slice(0, 3);
    return Object.assign({}, c, { focus, competitors: comps });
  }
  function renderFocusPanel() {
    const c = effectiveConfig();
    const sel = clear($("focus-select"));
    for (const d of state.config.destinations) sel.append(h("option", { value: d.id, text: d.name }));
    sel.value = c.focus;
    const chips = clear($("comp-chips"));
    for (const d of state.config.destinations) {
      if (d.id === c.focus) continue;
      const inp = h("input", { type: "checkbox", value: d.id });
      inp.checked = c.competitors.includes(d.id);
      inp.disabled = !inp.checked && c.competitors.length >= 3;
      inp.addEventListener("change", () => {
        const cur = effectiveConfig().competitors.filter((x) => x !== d.id);
        if (inp.checked) cur.push(d.id);
        state.competitors = cur;
        renderAll();
      });
      chips.append(h("label", { class: "chip-toggle" }, inp, h("span", { text: d.name })));
    }
    $("focus-panel").hidden = false;
  }

  // -------------------------------------------------------------------------
  // Render dashboard
  // -------------------------------------------------------------------------
  function heatColor(t) {
    t = Math.max(0, Math.min(1, t));
    const pos = t * (HEAT.length - 1), i = Math.floor(pos), f = pos - i;
    const a = HEAT[i], b = HEAT[Math.min(i + 1, HEAT.length - 1)];
    const ch = (x, k) => parseInt(x.slice(1 + k * 2, 3 + k * 2), 16);
    return `rgb(${[0, 1, 2].map((k) => Math.round(ch(a, k) + (ch(b, k) - ch(a, k)) * f)).join(",")})`;
  }
  function barChart(el, items, max) {
    clear(el);
    max = Math.max(max || 0, ...items.map((it) => Math.max(...it.series.map((s) => s.value))), 1);
    for (const it of items) {
      el.append(h("div", { class: "bar-row" },
        h("div", { class: "bar-label" + (it.focus ? " focus" : ""), text: it.label }),
        h("div", { class: "bar-track" }, it.series.map((s) => h("div", { class: "bar-line" },
          h("div", { class: "bar " + s.cls, style: { width: `${(s.value / max * 86).toFixed(2)}%` }, dataset: { tip: s.tip } }),
          h("span", { class: "bar-val", text: s.text }))))));
    }
  }
  function kpi(label, val, sub, extra, cls) {
    return h("div", { class: "kpi" + (cls ? " " + cls : "") }, h("div", { class: "k-label" }, label), h("div", { class: "k-val", text: val }), h("div", { class: "k-sub" }, sub), extra);
  }
  function meter(v, cls) { return h("div", { class: "meter" + (cls ? " " + cls : "") }, h("i", { style: { width: `${Math.max(0, Math.min(100, v)).toFixed(1)}%` } })); }

  function renderAll() {
    if (!state.records.length) return;
    const cfg = effectiveConfig();
    const res = analyze(state.records, cfg);
    state.results = res;
    const hd = res.headline;
    $("empty-state").hidden = true;
    $("dashboard").hidden = false;
    $("btn-export").disabled = false;
    renderFocusPanel();

    const chip = $("source-chip");
    chip.textContent = state.source;
    chip.className = "chip" + (state.kind === "live" ? " live" : state.kind === "demo" ? " sim" : "");
    $("source-line").textContent = `Sumber: ${state.source} · ${hd.responses_total} permintaan · model: ${hd.models.join(", ")}`;

    const banners = clear($("banners"));
    if (hd.simulated) banners.append(h("div", { class: "banner", role: "status" }, h("b", { text: "Data simulasi. " }), "Angka di bawah berasal dari mode demo, bukan jawaban LLM sungguhan."));
    if (hd.responses_error) banners.append(h("div", { class: "banner error", role: "status" }, `${hd.responses_error} dari ${hd.responses_total} permintaan gagal. Lihat tab Jawaban, filter status Gagal.`));

    const kp = clear($("kpis"));
    kp.append(kpi(`Share of AI voice ${hd.focus_name}`, pct(hd.focus_sov_pct),
      [h("span", { class: "rank-pill", text: `#${hd.focus_rank ?? "-"}` }), ` dari ${hd.destinations} destinasi`], null, "hero"));
    kp.append(kpi("Mention rate", pct(hd.focus_mention_rate_pct, 0), `${hd.focus_name} disebut di jawaban`, meter(hd.focus_mention_rate_pct)));
    for (const c of hd.competitors.slice(0, 1)) {
      kp.append(kpi(`vs ${c.name}`, c.focus_per_100 === null ? "-" : `${fx(c.focus_per_100, 0)} : 100`,
        `${hd.focus_name} per 100 sebutan ${c.name} (SOV ${c.name} ${pct(c.sov_pct)})`, meter(Math.min(100, c.focus_per_100 || 0), "comp")));
    }
    kp.append(kpi("Data", `${hd.responses_ok}`, `jawaban dari ${hd.models.length} model${hd.responses_error ? `, ${hd.responses_error} gagal` : ""}`));

    // head-to-head
    const byId = Object.fromEntries(res.summary.map((s) => [s.destination_id, s]));
    const h2hIds = [cfg.focus, ...cfg.competitors];
    const h2hMax = Math.max(1, ...h2hIds.map((id) => byId[id].share_of_voice_pct));
    const h2h = clear($("h2h"));
    for (const id of h2hIds) {
      const r = byId[id], g = groupOf(cfg, id);
      h2h.append(h("div", { class: "h2h-row" },
        h("div", { class: "h2h-name" }, r.destination, h("small", { text: `#${r.rank} · disebut di ${pct(r.mention_rate_pct, 0)} jawaban` })),
        h("div", { class: "h2h-bars" }, h("div", { class: "bar " + g, style: { width: `${(r.share_of_voice_pct / h2hMax * 100).toFixed(1)}%` },
          dataset: { tip: `${r.destination}\nShare of voice ${pct(r.share_of_voice_pct)}\n${r.mentions} sebutan` } })),
        h("div", { class: "h2h-val", text: pct(r.share_of_voice_pct) })));
    }
    if (!cfg.competitors.length) h2h.append(h("p", { class: "muted small", text: "Pilih pembanding di panel Fokus analisis." }));

    const ins = clear($("insights"));
    const list = buildInsights(res);
    if (!list.length) ins.append(h("li", { text: "Belum ada jawaban yang berhasil." }));
    for (const t of list) ins.append(h("li", { text: t }));

    renderRankTab(res, hd);
    renderLangTab(res);
    renderModelTab(res, cfg);
    renderCatTab(res, cfg);
    fillFilters(cfg);
    renderAnswers();
  }

  function renderRankTab(res, hd) {
    const s = res.summary;
    barChart($("chart-sov"), s.map((r) => ({ label: r.destination, focus: r.group === "focus",
      series: [{ value: r.share_of_voice_pct, cls: r.group, text: pct(r.share_of_voice_pct),
        tip: `${r.destination}\nShare of voice: ${pct(r.share_of_voice_pct)}\nSebutan: ${r.mentions}` }] })));
    barChart($("chart-rate"), s.slice().sort((a, b) => b.mention_rate_pct - a.mention_rate_pct).map((r) => ({ label: r.destination, focus: r.group === "focus",
      series: [{ value: r.mention_rate_pct, cls: r.group, text: pct(r.mention_rate_pct, 0),
        tip: `${r.destination}\nDisebut di ${r.responses_mentioned} dari ${hd.responses_ok} jawaban` }] })), 100);
    const t = clear($("summary-table"));
    t.append(h("thead", null, h("tr", null, ["#", "Destinasi", "Sebutan", "Jawaban yang menyebut", "Share of voice", "Mention rate", "Urutan pertama"]
      .map((x, i) => h("th", { class: i >= 2 ? "num" : null, text: x })))));
    t.append(h("tbody", null, s.map((r) => h("tr", { class: r.group === "focus" ? "is-focus" : null, dataset: { dest: r.destination_id } },
      h("td", { text: r.rank }), h("td", null, h("i", { class: "sw " + r.group }), " ", r.destination),
      h("td", { class: "num", text: r.mentions }), h("td", { class: "num", text: r.responses_mentioned }),
      h("td", { class: "num", text: pct(r.share_of_voice_pct) }), h("td", { class: "num", text: pct(r.mention_rate_pct) }),
      h("td", { class: "num", text: r.avg_first_rank === null ? "" : fx(r.avg_first_rank, 2) })))));
  }
  function renderLangTab(res) {
    const langs = Array.from(new Set(res.by_language.map((r) => r.language))).sort((a, b) => (a === "id" ? -1 : b === "id" ? 1 : cmp(a, b)));
    const lk = {}; for (const r of res.by_language) lk[r.language + "|" + r.destination_id] = r;
    barChart($("chart-lang"), res.summary.map((d) => ({ label: d.destination, focus: d.group === "focus",
      series: langs.map((l) => { const r = lk[l + "|" + d.destination_id]; const v = r ? r.share_of_voice_pct : 0;
        return { value: v, cls: "lang-" + l, text: pct(v), tip: `${d.destination}\n${LANG_LABELS[l] || l}: ${pct(v)} (${r ? r.mentions : 0} sebutan)` }; }) })));
  }
  function heatTable(el, rowKeys, rowLabel, colKeys, colLabel, valueOf, opts) {
    clear(el);
    let vmax = 1;
    for (const rk of rowKeys) for (const ck of colKeys) vmax = Math.max(vmax, valueOf(rk, ck));
    el.append(h("thead", null, h("tr", null, h("th", { class: "rowh", text: opts.corner }),
      colKeys.map((ck) => h("th", { class: opts.colClass ? opts.colClass(ck) : null, text: colLabel(ck) })))));
    el.append(h("tbody", null, rowKeys.map((rk) => h("tr", { class: opts.rowClass ? opts.rowClass(rk) : null },
      h("th", { class: "rowh", text: rowLabel(rk) }),
      colKeys.map((ck) => { const v = valueOf(rk, ck), t = v / vmax;
        return h("td", { class: "cell", style: { background: heatColor(t), color: t > 0.55 ? "#ffffff" : "#0b0b0b" },
          dataset: { tip: `${rowLabel(rk)} | ${colLabel(ck)}\n${pct(v)}` }, text: pct(v) }); })))));
  }
  function renderModelTab(res, cfg) {
    const models = Array.from(new Set(res.by_model.map((r) => r.model_label))).sort();
    const mk = {}; for (const r of res.by_model) mk[r.model_label + "|" + r.destination_id] = r.share_of_voice_pct;
    heatTable($("heat-model"), res.summary.map((s) => s.destination_id), (id) => destName(cfg, id), models, (m) => m,
      (id, m) => mk[m + "|" + id] || 0, { corner: "Destinasi", rowClass: (id) => (id === cfg.focus ? "is-focus" : null) });
  }
  function renderCatTab(res, cfg) {
    const cats = Array.from(new Set(res.by_category.map((r) => r.category)));
    const ck = {}; for (const r of res.by_category) ck[r.category + "|" + r.destination_id] = r.share_of_voice_pct;
    const cols = [cfg.focus, ...cfg.competitors, ...res.summary.map((s) => s.destination_id).filter((id) => id !== cfg.focus && !cfg.competitors.includes(id))];
    heatTable($("heat-cat"), cats, (c) => c || "(tanpa kategori)", cols, (id) => destName(cfg, id), (c, id) => ck[c + "|" + id] || 0,
      { corner: "Kategori", colClass: (id) => (id === cfg.focus ? "colfocus" : null) });
  }

  // -------------------------------------------------------------------------
  // Penjelajah jawaban
  // -------------------------------------------------------------------------
  function fillSelect(el, values, allLabel, labeler) {
    const cur = el.value;
    clear(el).append(h("option", { value: "", text: allLabel }));
    for (const v of values) el.append(h("option", { value: v, text: labeler ? labeler(v) : v }));
    if (values.includes(cur)) el.value = cur;
  }
  function fillFilters(cfg) {
    fillSelect($("f-model"), Array.from(new Set(state.records.map((r) => r.model_label))).sort(), "Semua model");
    fillSelect($("f-lang"), Array.from(new Set(state.records.map((r) => r.language))).sort(), "Semua bahasa", (l) => LANG_SHORT[l] || l);
    fillSelect($("f-dest"), cfg.destinations.map((d) => d.id), "Semua destinasi", (id) => `Menyebut ${destName(cfg, id)}`);
  }
  function displayText(text) {
    // Tampilan saja: buang penanda markdown (**tebal**, __, judul #). Penghitungan tetap memakai teks asli.
    return String(text || "").replace(/\*\*|__/g, "").replace(/^#{1,6}\s+/gm, "");
  }
  function highlighted(text, matchers, cfg) {
    const { norm, spans } = findSpans(displayText(text), matchers);
    const frag = document.createDocumentFragment();
    let pos = 0;
    for (const [a, b, d] of spans) {
      frag.append(norm.slice(pos, a), h("mark", { class: groupOf(cfg, d), title: destName(cfg, d), text: norm.slice(a, b) }));
      pos = b;
    }
    frag.append(norm.slice(pos));
    return frag;
  }
  function filteredRecords(cfg, matchers) {
    const fm = $("f-model").value, fl = $("f-lang").value, fd = $("f-dest").value, fs = $("f-status").value;
    const q = $("f-search").value.trim().toLowerCase();
    return state.records.filter((r) => (!fm || r.model_label === fm) && (!fl || r.language === fl) && (!fs || r.status === fs)
      && (!q || (r.prompt + "\n" + r.response).toLowerCase().includes(q))
      && (!fd || (r.status === "ok" && scanText(r.response, matchers)[fd][0] > 0)));
  }
  function renderAnswers() {
    const cfg = effectiveConfig(), matchers = buildMatchers(cfg.destinations);
    const list = filteredRecords(cfg, matchers);
    $("answers-count").textContent = String(state.records.length);
    $("resp-count").textContent = `${list.length} jawaban cocok. Sorotan biru = fokus, oranye = pembanding.`;
    const box = clear($("responses"));
    for (const r of list.slice(0, state.shown)) {
      const meta = h("div", { class: "answer-meta" }, h("span", { class: "tag", text: r.model_label }),
        h("span", { class: "tag", text: `${r.question_id} · ${LANG_SHORT[r.language] || r.language}` }),
        r.category ? h("span", { class: "tag", text: r.category }) : null,
        r.status !== "ok" ? h("span", { class: "tag err", text: "gagal" }) : null);
      const card = h("article", { class: "answer" }, meta, h("p", { class: "answer-q", text: r.prompt }));
      if (r.status !== "ok") card.append(h("p", { class: "answer-text", text: r.error || "tanpa pesan error" }));
      else {
        const long = r.response.length > 420;
        const body = h("p", { class: "answer-text" + (long ? " clamp" : "") }, highlighted(r.response, matchers, cfg));
        card.append(body);
        if (long) card.append(h("button", { class: "more", type: "button", text: "Selengkapnya", onclick: (e) => {
          const open = body.classList.toggle("clamp"); e.target.textContent = open ? "Selengkapnya" : "Ringkas"; } }));
        const hits = scanText(r.response, matchers);
        const tags = cfg.destinations.filter((d) => hits[d.id][0] > 0).map((d) => h("span", { class: "tag", text: `${d.name} x${hits[d.id][0]}` }));
        if (tags.length) card.append(h("div", { class: "answer-hits" }, tags));
      }
      box.append(card);
    }
    if (!list.length) box.append(h("p", { class: "muted", text: "Tidak ada jawaban yang cocok dengan filter." }));
    $("more-btn").hidden = list.length <= state.shown;
  }

  // -------------------------------------------------------------------------
  // Sumber data
  // -------------------------------------------------------------------------
  function setData(records, source, kind, cfg) {
    const recs = records.slice(0, LIMITS.records).map(sanitizeRecord);
    state.records = recs;
    state.source = source;
    state.kind = kind;
    state.config = cfg || state.defaultConfig;
    state.shown = PAGE;
    renderAll();
  }
  async function loadDemo() {
    try {
      const r = await fetch("data/demo_results.json", { cache: "no-store", credentials: "omit" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setData(data.responses, "Demo · data simulasi", "demo", validConfig(data.config) ? pickConfig(data.config) : null);
      closeDrawer();
    } catch (e) { toast(`Gagal memuat demo: ${e.message}`, "error"); }
  }
  async function handleFile(file) {
    if (!file) return;
    if (file.size > LIMITS.fileBytes) { toast("File terlalu besar (maks. 25 MB).", "error"); return; }
    try {
      const text = await file.text();
      let recs, cfg = null;
      if (/\.json$/i.test(file.name)) {
        const data = JSON.parse(text.replace(/^﻿/, ""));
        recs = Array.isArray(data) ? data : data && data.responses;
        if (data && data.config) {
          if (validConfig(data.config)) cfg = pickConfig(data.config);
          else toast("Konfigurasi di file tidak valid; memakai konfigurasi bawaan.", "error");
        }
      } else recs = parseCSV(text);
      if (!Array.isArray(recs) || !recs.length) throw new Error("tidak ada data jawaban");
      if (!("response" in recs[0]) || !("model" in recs[0] || "model_label" in recs[0])) throw new Error("kolom 'response' dan 'model' wajib ada");
      if (recs.length > LIMITS.records) toast(`Hanya ${LIMITS.records} baris pertama yang dimuat.`);
      state.focus = null; state.competitors = null;
      setData(recs, `File · ${file.name.slice(0, 60)}`, "file", cfg);
      toast(`${Math.min(recs.length, LIMITS.records)} jawaban dimuat dari ${file.name}.`);
      closeDrawer();
    } catch (e) { toast(`File tidak bisa dibaca: ${e.message}`, "error"); }
  }

  // -------------------------------------------------------------------------
  // Audit langsung dari browser
  // -------------------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  function redact(text, keys) {
    let s = String(text || "");
    for (const k of keys) if (k && k.length >= 6) s = s.split(k).join("[REDACTED]");
    return s.replace(/(sk-ant-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|gsk_[A-Za-z0-9]{16,})/g, "[REDACTED]");
  }
  async function postJSON(url, headers, body, signal) {
    for (let attempt = 0; ; attempt++) {
      let resp;
      try {
        resp = await fetch(url, { method: "POST", headers: Object.assign({ "content-type": "application/json" }, headers),
          body: JSON.stringify(body), signal, redirect: "error", credentials: "omit", referrerPolicy: "no-referrer", cache: "no-store" });
      } catch (e) {
        if (signal && signal.aborted) throw e;
        if (attempt < 3) { await sleep(1000 * 2 ** attempt); continue; }
        throw new Error(`koneksi gagal (${e.message}); provider mungkin memblokir akses browser (CORS)`);
      }
      if (resp.ok) return resp.json();
      let msg = resp.statusText, raw = "";
      try { raw = await resp.text(); const j = JSON.parse(raw); const err = Array.isArray(j) ? j[0].error : j.error; msg = (err && (err.message || err.type)) || raw.slice(0, 300); } catch (_) { msg = raw.slice(0, 300) || msg; }
      if ([408, 409, 425, 429, 500, 502, 503, 504, 529].includes(resp.status) && attempt < 3) {
        const ra = parseFloat(resp.headers.get("retry-after"));
        await sleep(Number.isFinite(ra) ? Math.min(ra, 60) * 1000 : 1000 * 2 ** attempt);
        continue;
      }
      const err = new Error(`HTTP ${resp.status}: ${msg}`); err.status = resp.status; err.raw = raw; throw err;
    }
  }
  function claudeSupportsEffort(m) { return /^claude-(opus|sonnet|fable|haiku|mythos)-5/.test(m) || /^claude-(opus-4-[5678]|sonnet-4-6)/.test(m); }
  async function callProvider(p, model, prompt, key, signal) {
    const info = PROVIDERS[p], base = info.base;
    if (info.kind === "anthropic") {
      const headers = { "x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "anthropic-dangerous-direct-browser-access": "true" };
      const body = { model, max_tokens: 4000, messages: [{ role: "user", content: prompt }] };
      if (claudeSupportsEffort(model)) body.output_config = { effort: "low" };
      const fb = CLAUDE_FALLBACK_MODELS.has(model);
      if (fb) { headers["anthropic-beta"] = "server-side-fallback-2026-07-01"; body.fallbacks = "default"; }
      let data;
      try { data = await postJSON(`${base}/v1/messages`, headers, body, signal); } catch (e) {
        if (fb && e.status === 400 && /fallback/i.test(e.message + e.raw)) {
          delete headers["anthropic-beta"]; delete body.fallbacks;
          data = await postJSON(`${base}/v1/messages`, headers, body, signal);
        } else throw e;
      }
      if (data.stop_reason === "refusal") throw new Error("model menolak menjawab (refusal)");
      const text = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
      return { text, stop_reason: data.stop_reason, input_tokens: data.usage && data.usage.input_tokens, output_tokens: data.usage && data.usage.output_tokens };
    }
    if (info.kind === "gemini") {
      const data = await postJSON(`${base}/models/${encodeURIComponent(model)}:generateContent`, { "x-goog-api-key": key },
        { contents: [{ role: "user", parts: [{ text: prompt }] }] }, signal);
      const c = (data.candidates || [])[0];
      if (!c) throw new Error(`Gemini tidak mengembalikan jawaban (${(data.promptFeedback || {}).blockReason || "tanpa kandidat"})`);
      const text = ((c.content || {}).parts || []).filter((x) => !x.thought).map((x) => x.text || "").join("");
      const u = data.usageMetadata || {};
      return { text, stop_reason: c.finishReason, input_tokens: u.promptTokenCount, output_tokens: (u.candidatesTokenCount || 0) + (u.thoughtsTokenCount || 0) };
    }
    const headers = key ? { authorization: `Bearer ${key}` } : {};
    if (p === "openrouter") headers["x-title"] = "GEM Visibility Auditor";
    const data = await postJSON(`${base}/chat/completions`, headers, { model, messages: [{ role: "user", content: prompt }] }, signal);
    const ch = (data.choices || [])[0];
    if (!ch) throw new Error("respons tidak berisi 'choices'");
    let content = (ch.message || {}).content || "";
    if (Array.isArray(content)) content = content.map((x) => x.text || "").join("");
    const u = data.usage || {};
    return { text: content, stop_reason: ch.finish_reason, input_tokens: u.prompt_tokens, output_tokens: u.completion_tokens };
  }

  function askConsent(hosts) {
    try { if (sessionStorage.getItem("gem-consent") === "1") return Promise.resolve(true); } catch (_) { /* abaikan */ }
    const dlg = $("consent-dialog");
    clear($("consent-hosts"));
    for (const host of hosts) $("consent-hosts").append(h("li", { text: host }));
    $("consent-check").checked = false;
    $("consent-ok").disabled = true;
    return new Promise((resolve) => {
      dlg.addEventListener("close", () => {
        const ok = dlg.returnValue === "ok";
        if (ok) { try { sessionStorage.setItem("gem-consent", "1"); } catch (_) { /* abaikan */ } }
        resolve(ok);
      }, { once: true });
      dlg.showModal();
    });
  }

  async function runAudit() {
    if (state.running) return;
    const cfg = state.defaultConfig;
    const langs = selectedLangs();
    const maxq = parseInt($("run-maxq").value, 10);
    const runs = Math.max(1, Math.min(5, parseInt($("run-runs").value, 10) || 1));
    const models = [], keys = {};
    for (const row of document.querySelectorAll(".prov")) {
      if (!row.querySelector(".p-on").checked) continue;
      const p = row.dataset.p, info = PROVIDERS[p], keyEl = row.querySelector(".p-key");
      const key = keyEl ? keyEl.value.trim() : "";
      if (info.key && !key) { toast(`Kunci API ${info.name} belum diisi.`, "error"); openDrawer(); keyEl.focus(); return; }
      keys[p] = key;
      for (const m of row.querySelector(".p-model").value.split(",").map((x) => x.trim()).filter(Boolean)) models.push({ p, m });
    }
    if (!models.length) { toast("Aktifkan minimal satu model.", "error"); return; }
    if (!langs.length) { toast("Pilih minimal satu bahasa.", "error"); return; }
    const hosts = Array.from(new Set(models.filter((x) => PROVIDERS[x.p].key).map((x) => new URL(PROVIDERS[x.p].base).host)));
    if (hosts.length && !(await askConsent(hosts))) return;

    const tasks = [];
    for (const md of models) for (const q of cfg.questions.slice(0, maxq)) for (const lang of langs) {
      const prompt = q.text[lang]; if (!prompt) continue;
      for (let run = 1; run <= runs; run++) tasks.push({ md, rec: { response_id: `${md.p}:${md.m}|${q.qid}|${lang}|${run}`, provider: md.p,
        model: md.m, model_label: `${md.p}:${md.m}`, question_id: q.qid, category: q.category || "", language: lang, run, prompt } });
    }
    const ctrl = new AbortController();
    Object.assign(state, { running: true, abort: ctrl, focus: null, competitors: null });
    refreshControls();
    closeDrawer();
    const startedAt = Date.now(), records = [], perModel = new Map();
    for (const t of tasks) { const k = t.rec.model_label; perModel.set(k, perModel.get(k) || { total: 0, done: 0, ok: 0 }); perModel.get(k).total++; }
    $("run-panel").hidden = false; $("empty-state").hidden = true;
    $("run-title").textContent = "Audit berjalan";
    $("run-sub").textContent = `${tasks.length} permintaan ke ${perModel.size} model. Hasil diperbarui langsung.`;
    $("stop-btn").hidden = false;
    clear($("run-feed"));
    let done = 0, okN = 0, next = 0, pendingRender = false;
    const scheduleRender = () => {
      if (pendingRender) return;
      pendingRender = true;
      setTimeout(() => { pendingRender = false; state.records = records.slice(); state.config = cfg; state.source = `Audit langsung · ${perModel.size} model`; state.kind = "live"; renderAll(); }, 400);
    };
    const updateRun = (rec) => {
      $("progress-bar").style.width = `${(done / tasks.length * 100).toFixed(1)}%`;
      const secs = Math.round((Date.now() - startedAt) / 1000);
      const stats = clear($("run-stats"));
      for (const [v, l] of [[`${done}/${tasks.length}`, "selesai"], [okN, "berhasil"], [done - okN, "gagal"], [`${secs}s`, "waktu"]]) stats.append(h("div", { class: "stat" }, h("b", { text: v }), h("span", { text: l })));
      const rm = clear($("run-models"));
      for (const [k, v] of perModel) rm.append(h("div", { class: "rm-row" }, h("span", { text: k }), meter(v.done / v.total * 100), h("span", { class: "num", text: `${v.done}/${v.total}` })));
      if (rec) {
        const feed = $("run-feed");
        feed.prepend(h("li", { class: rec.status === "ok" ? null : "err", text: `${rec.status === "ok" ? "ok " : "ERR"} ${rec.model_label} ${rec.question_id}-${rec.language}${rec.status === "ok" ? "" : "  " + rec.error.slice(0, 120)}` }));
        while (feed.children.length > 8) feed.lastChild.remove();
      }
    };
    updateRun();
    const worker = async () => {
      while (next < tasks.length && !ctrl.signal.aborted) {
        const t = tasks[next++];
        const rec = Object.assign({}, t.rec, { timestamp: new Date().toISOString().slice(0, 19), simulated: false });
        const t0 = performance.now();
        try {
          const r = await callProvider(t.md.p, t.md.m, rec.prompt, keys[t.md.p], ctrl.signal);
          const okText = String(r.text || "").trim().length > 0;
          Object.assign(rec, { response: String(r.text || ""), status: okText ? "ok" : "error", error: okText ? "" : "jawaban kosong",
            stop_reason: r.stop_reason ?? null, input_tokens: r.input_tokens ?? null, output_tokens: r.output_tokens ?? null });
        } catch (e) {
          Object.assign(rec, { response: "", status: "error", error: ctrl.signal.aborted ? "dihentikan" : redact(e.message, Object.values(keys)).slice(0, 500),
            stop_reason: null, input_tokens: null, output_tokens: null });
        }
        rec.latency_s = Math.round((performance.now() - t0) / 10) / 100;
        records.push(rec); done++; if (rec.status === "ok") okN++;
        const pm = perModel.get(rec.model_label); pm.done++; if (rec.status === "ok") pm.ok++;
        updateRun(rec); scheduleRender();
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    for (const k of Object.keys(keys)) keys[k] = ""; // lepaskan referensi kunci
    const order = Object.fromEntries(tasks.map((t, i) => [t.rec.response_id, i]));
    records.sort((a, b) => order[a.response_id] - order[b.response_id]);
    Object.assign(state, { running: false, abort: null });
    $("run-panel").hidden = true;
    refreshControls();
    if (records.length) setData(records, `Audit langsung · ${perModel.size} model`, "live", cfg);
    if (ctrl.signal.aborted) toast(`Audit dihentikan: ${okN} jawaban tersimpan.`);
    else if (!okN && records.length) toast(`Semua permintaan gagal. Contoh: ${records[0].error}`, "error");
    else toast(`Audit selesai: ${okN} berhasil, ${done - okN} gagal.`);
  }

  // -------------------------------------------------------------------------
  // Ekspor
  // -------------------------------------------------------------------------
  function download(name, content, type) {
    const a = h("a", { href: URL.createObjectURL(new Blob([content], { type })), download: name });
    document.body.append(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function doExport(kind) {
    if (!state.results) return;
    const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
    if (kind === "responses") download(`responses_${stamp}.csv`, toCSV(state.records, RESPONSE_COLUMNS), "text/csv");
    else if (kind === "summary") download(`summary_${stamp}.csv`, toCSV(state.results.summary,
      ["rank", "destination_id", "destination", "group", "mentions", "responses_mentioned", "share_of_voice_pct", "mention_rate_pct", "avg_first_rank"]), "text/csv");
    else if (kind === "json") download(`dashboard_data_${stamp}.json`, JSON.stringify({
      meta: { tool: "GEM Visibility Auditor (web)", generated: new Date().toISOString(), source: state.source },
      config: effectiveConfig(), headline: state.results.headline, insights: buildInsights(state.results), responses: state.records }, null, 1), "application/json");
    else if (kind === "print") window.print();
  }

  // -------------------------------------------------------------------------
  // Navigasi, tema, interaksi
  // -------------------------------------------------------------------------
  function selectSource(src) {
    for (const b of document.querySelectorAll(".seg-btn")) { const on = b.dataset.src === src; b.classList.toggle("active", on); b.setAttribute("aria-selected", String(on)); }
    for (const p of document.querySelectorAll("[data-panel]")) p.hidden = p.dataset.panel !== src;
  }
  function selectTab(tab) {
    state.tab = tab;
    for (const b of document.querySelectorAll(".tab")) { const on = b.dataset.tab === tab; b.classList.toggle("active", on); b.setAttribute("aria-selected", String(on)); }
    for (const p of document.querySelectorAll("[data-tabpanel]")) p.hidden = p.dataset.tabpanel !== tab;
  }
  function openDrawer() { $("sidebar").classList.add("open"); $("scrim").hidden = false; $("btn-menu").setAttribute("aria-expanded", "true"); }
  function closeDrawer() { $("sidebar").classList.remove("open"); $("scrim").hidden = true; $("btn-menu").setAttribute("aria-expanded", "false"); }
  function applyTheme(t) {
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  }
  function wire() {
    for (const b of document.querySelectorAll(".seg-btn")) b.addEventListener("click", () => selectSource(b.dataset.src));
    for (const c of document.querySelectorAll(".action-card")) c.addEventListener("click", () => {
      selectSource(c.dataset.go);
      if (c.dataset.go === "demo") { loadDemo(); return; }
      openDrawer();
      const target = c.dataset.go === "import" ? $("file-input")
        : Array.from(document.querySelectorAll(".prov.on .p-key")).find((k) => !k.value) || $("run-btn");
      if (c.dataset.go === "import") $("dropzone").focus(); else target.focus();
    });
    for (const t of document.querySelectorAll(".tab")) t.addEventListener("click", () => selectTab(t.dataset.tab));
    $("load-demo").addEventListener("click", () => { state.focus = null; state.competitors = null; loadDemo(); });
    $("file-input").addEventListener("change", (e) => { handleFile(e.target.files[0]); e.target.value = ""; });
    const dz = $("dropzone");
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
    dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); handleFile(e.dataTransfer.files[0]); });
    $("run-btn").addEventListener("click", runAudit);
    $("stop-btn").addEventListener("click", () => { if (state.abort) state.abort.abort(); });
    $("clear-keys").addEventListener("click", () => { for (const k of document.querySelectorAll(".p-key")) k.value = ""; refreshControls(); toast("Semua kunci API dihapus dari halaman."); });
    for (const el of document.querySelectorAll("#lang-chips input")) el.addEventListener("change", () => { refreshControls(); storePrefs(); });
    $("run-maxq").addEventListener("input", () => { refreshControls(); storePrefs(); });
    $("run-runs").addEventListener("change", () => { refreshControls(); storePrefs(); });
    $("runs-dec").addEventListener("click", () => { $("run-runs").value = String(Math.max(1, (parseInt($("run-runs").value, 10) || 1) - 1)); refreshControls(); storePrefs(); });
    $("runs-inc").addEventListener("click", () => { $("run-runs").value = String(Math.min(5, (parseInt($("run-runs").value, 10) || 1) + 1)); refreshControls(); storePrefs(); });
    $("focus-select").addEventListener("change", (e) => {
      state.focus = e.target.value;
      state.competitors = effectiveConfig().competitors.filter((x) => x !== state.focus);
      renderAll();
    });
    for (const id of ["f-model", "f-lang", "f-dest", "f-status"]) $(id).addEventListener("change", () => { state.shown = PAGE; renderAnswers(); });
    let timer = null;
    $("f-search").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.shown = PAGE; renderAnswers(); }, 200); });
    $("more-btn").addEventListener("click", () => { state.shown += PAGE; renderAnswers(); });
    $("btn-menu").addEventListener("click", () => ($("sidebar").classList.contains("open") ? closeDrawer() : openDrawer()));
    $("scrim").addEventListener("click", closeDrawer);
    const menu = $("export-menu"), btn = $("btn-export");
    btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", String(!menu.hidden)); });
    for (const b of menu.querySelectorAll("[data-export]")) b.addEventListener("click", () => { menu.hidden = true; doExport(b.dataset.export); });
    document.addEventListener("click", () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.hidden = true; closeDrawer(); } });
    $("btn-help").addEventListener("click", () => $("help-dialog").showModal());
    $("help-close").addEventListener("click", () => $("help-dialog").close());
    $("consent-check").addEventListener("change", (e) => { $("consent-ok").disabled = !e.target.checked; });
    $("btn-theme").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      const t = dark ? "light" : "dark";
      applyTheme(t); prefs.theme = t; savePrefs(prefs);
    });
    // Bersihkan kunci saat halaman ditutup / masuk back-forward cache.
    window.addEventListener("pagehide", () => { for (const k of document.querySelectorAll(".p-key")) k.value = ""; });
    const tip = $("tooltip");
    document.addEventListener("mousemove", (e) => {
      const t = e.target.closest && e.target.closest("[data-tip]");
      if (!t) { tip.hidden = true; return; }
      tip.textContent = t.dataset.tip; tip.hidden = false;
      tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8)}px`;
      tip.style.top = `${Math.min(e.clientY + 14, window.innerHeight - tip.offsetHeight - 8)}px`;
    });
  }

  async function init() {
    applyTheme(prefs.theme);
    wire();
    if (Array.isArray(prefs.langs)) for (const el of document.querySelectorAll("#lang-chips input")) el.checked = prefs.langs.includes(el.value);
    if (prefs.maxq) $("run-maxq").value = String(prefs.maxq);
    if (prefs.runs) $("run-runs").value = String(prefs.runs);
    buildProviders();
    try {
      const r = await fetch("data/config.json", { cache: "no-store", credentials: "omit" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const c = await r.json();
      if (!validConfig(c)) throw new Error("konfigurasi tidak valid");
      state.defaultConfig = pickConfig(c);
      state.config = state.defaultConfig;
    } catch (e) {
      toast(`Gagal memuat konfigurasi: ${e.message}. Buka lewat GitHub Pages atau "python -m http.server" di folder docs.`, "error");
      return;
    }
    buildQuestionList();
    refreshControls();
    if (new URLSearchParams(location.search).get("demo") === "1") { selectSource("demo"); await loadDemo(); }
    document.body.dataset.ready = "1";
  }

  window.__gem = { state, analyze, buildInsights, parseCSV, buildMatchers, scanText, findSpans, toCSV, sanitizeRecord, validConfig };
  init();
})();
