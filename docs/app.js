/* GEM Visibility Auditor: dashboard web (GitHub Pages).
 * Logika analisis di file ini adalah cermin dari gem_visibility_auditor.py
 * (alias, regex batas kata, share of voice, mention rate, urutan pertama),
 * sehingga hasil di browser sama dengan hasil skrip Python. */
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
  const HEAT = ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];
  const RUN_PROVIDERS = {
    anthropic: { label: "Claude (Anthropic)", model: "claude-opus-5-5", base: "https://api.anthropic.com", keyName: "ANTHROPIC_API_KEY" },
    gemini: { label: "Gemini (Google)", model: "gemini-flash-latest", base: "https://generativelanguage.googleapis.com/v1beta", keyName: "GEMINI_API_KEY" },
    openai: { label: "ChatGPT (OpenAI)", model: "gpt-5-mini", base: "https://api.openai.com/v1", keyName: "OPENAI_API_KEY" },
    openrouter: { label: "OpenRouter", model: "meta-llama/llama-3.3-70b-instruct", base: "https://openrouter.ai/api/v1", keyName: "OPENROUTER_API_KEY" },
    custom: { label: "OpenAI-compatible lain (Groq, DeepSeek, Ollama)", model: "", base: "", keyName: "API key (opsional)", customBase: true },
  };

  const state = { config: null, defaultConfig: null, records: [], source: "", results: null, abort: null, running: false };
  const $ = (id) => document.getElementById(id);

  // -------------------------------------------------------------------------
  // Analisis (cermin Python)
  // -------------------------------------------------------------------------
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function aliasPattern(a) {
    return a.normalize("NFKC").toLowerCase().trim().split(/\s+/).map(escapeRe).join("[\\s\\-]+");
  }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function buildMatchers(dests) {
    return dests.map((d) => {
      const al = Array.from(new Set(d.aliases.filter((a) => a.trim()))).sort((a, b) => (b.length - a.length) || cmp(a, b));
      const body = al.map(aliasPattern).join("|");
      return { id: d.id, re: new RegExp("(?<![\\p{L}\\p{N}_])(?:" + body + ")(?![\\p{L}\\p{N}_])", "giu") };
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
  function groupOf(cfg, id) {
    if (id === cfg.focus) return "focus";
    if (cfg.competitors.includes(id)) return "competitor";
    return "other";
  }
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
      return {
        destination_id: d.id, destination: d.name, group: groupOf(cfg, d.id), mentions: a.mentions,
        responses_mentioned: a.rm, sov: total ? a.mentions / total * 100 : 0, rate: n ? a.rm / n * 100 : 0,
        avg_first_rank: a.rankN ? a.rankSum / a.rankN : null,
      };
    });
    t.sort((x, y) => (y.sov - x.sov) || (order[x.destination_id] - order[y.destination_id]));
    return t.map((r, i) => ({
      rank: i + 1, destination_id: r.destination_id, destination: r.destination, group: r.group,
      mentions: r.mentions, responses_mentioned: r.responses_mentioned,
      share_of_voice_pct: round2(r.sov), mention_rate_pct: round2(r.rate),
      avg_first_rank: r.avg_first_rank === null ? null : round2(r.avg_first_rank),
    }));
  }

  function analyze(records, cfg) {
    const ok = records.filter((r) => r.status === "ok");
    const matchers = buildMatchers(cfg.destinations);
    const rows = [];
    for (const r of ok) {
      const hits = scanText(r.response, matchers);
      const ranked = Object.entries(hits).filter(([, v]) => v[0] > 0).map(([d, v]) => [v[1], d])
        .sort((a, b) => (a[0] - b[0]) || cmp(a[1], b[1]));
      const rankOf = {}; ranked.forEach(([, d], i) => { rankOf[d] = i + 1; });
      for (const d of cfg.destinations) {
        const cnt = hits[d.id][0];
        rows.push({
          response_id: r.response_id, model_label: r.model_label, language: r.language, category: r.category,
          question_id: r.question_id, destination_id: d.id, count: cnt, mentioned: cnt > 0,
          first_rank: rankOf[d.id] || null,
        });
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
      focus_rank: ok.length ? f.rank : null, focus_mention_rate_pct: f.mention_rate_pct,
      destinations: cfg.destinations.length, responses_ok: ok.length, responses_total: records.length,
      responses_error: records.length - ok.length,
      models: Array.from(new Set(records.map((r) => r.model_label))).sort(),
      simulated: records.some((r) => r.simulated === true || String(r.simulated).toLowerCase() === "true"),
      competitors: cfg.competitors.map((c) => {
        const s = byId[c];
        return {
          id: c, name: destName(cfg, c), sov_pct: s.share_of_voice_pct, mention_rate_pct: s.mention_rate_pct,
          focus_per_100: s.share_of_voice_pct ? Math.round(f.share_of_voice_pct / s.share_of_voice_pct * 1000) / 10 : null,
        };
      }),
    };
    return { mentions: rows, summary, by_language: by("language"), by_model: by("model_label"), by_category: by("category"), headline };
  }

  // -------------------------------------------------------------------------
  // CSV
  // -------------------------------------------------------------------------
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    const rows = []; let row = [], field = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== "\r") field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    const head = rows.shift() || [];
    return rows.filter((r) => r.length > 1 || r[0] !== "").map((r) => Object.fromEntries(head.map((h, j) => [h, r[j] === undefined ? "" : r[j]])));
  }
  function csvCell(v) {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function toCSV(rows, cols) {
    return "﻿" + [cols.join(",")].concat(rows.map((r) => cols.map((c) => csvCell(r[c])).join(","))).join("\n") + "\n";
  }
  function normalizeRecords(recs) {
    return recs.map((r) => {
      const o = Object.assign({}, r);
      o.response = o.response == null ? "" : String(o.response);
      o.status = o.status || "ok";
      o.model_label = o.model_label || `${o.provider}:${o.model}`;
      o.response_id = o.response_id || `${o.model_label}|${o.question_id}|${o.language}|${o.run}`;
      return o;
    });
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v, d = 1) => `${Number(v).toFixed(d)}%`;

  function barChart(el, items, max) {
    max = Math.max(max || 0, ...items.map((it) => Math.max(...it.series.map((s) => s.value))), 1);
    el.innerHTML = items.map((it) => `
      <div class="bar-row"><div class="bar-label ${it.labelCls || ""}">${esc(it.label)}</div>
      <div class="bar-track">${it.series.map((s) => `
        <div class="bar-line"><div class="bar ${s.cls}" style="width:${(s.value / max * 88).toFixed(2)}%" data-tip="${esc(s.tip)}"></div>
        ${s.showVal === false ? "" : `<span class="bar-val">${esc(s.text)}</span>`}</div>`).join("")}
      </div></div>`).join("");
  }

  function heatColor(t) {
    t = Math.max(0, Math.min(1, t));
    const pos = t * (HEAT.length - 1), i = Math.floor(pos), f = pos - i;
    const a = HEAT[i], b = HEAT[Math.min(i + 1, HEAT.length - 1)];
    const ch = (h, k) => parseInt(h.slice(1 + k * 2, 3 + k * 2), 16);
    const mix = [0, 1, 2].map((k) => Math.round(ch(a, k) + (ch(b, k) - ch(a, k)) * f));
    return `rgb(${mix.join(",")})`;
  }

  function render() {
    const cfg = state.config, recs = state.records;
    const res = analyze(recs, cfg);
    state.results = res;
    const h = res.headline;
    $("results").classList.remove("hidden");
    $("sim-banner").classList.toggle("hidden", !h.simulated);
    $("meta-line").textContent = `${h.responses_ok} jawaban berhasil, ${h.responses_error} gagal, dari ${h.models.length} model: ${h.models.join(", ")}. Sumber: ${state.source}`;

    const tiles = [`<div class="tile hero"><div class="lbl">Share of AI voice ${esc(h.focus_name)}</div>
      <div class="val">${pct(h.focus_sov_pct)}</div>
      <div class="sub">Peringkat ${h.focus_rank ?? "-"} dari ${h.destinations}, disebut di ${pct(h.focus_mention_rate_pct)} jawaban</div></div>`];
    for (const c of h.competitors) {
      tiles.push(`<div class="tile"><div class="lbl">Share of AI voice ${esc(c.name)}</div><div class="val">${pct(c.sov_pct)}</div>
        <div class="sub">${esc(h.focus_name)} disebut ${c.focus_per_100 ?? "-"} kali per 100 sebutan ${esc(c.name)}</div></div>`);
    }
    $("tiles").innerHTML = tiles.join("");
    $("headline").textContent = h.competitors.map((c) => `vs ${c.name}: ${pct(c.sov_pct)} SOV`).join(" | ");

    const s = res.summary;
    barChart($("chart-sov"), s.map((r) => ({
      label: r.destination, labelCls: r.group === "focus" ? "focus" : "",
      series: [{ value: r.share_of_voice_pct, cls: r.group, text: pct(r.share_of_voice_pct),
        tip: `${r.destination}\nShare of voice: ${pct(r.share_of_voice_pct)}\nSebutan: ${r.mentions}\nJawaban yang menyebut: ${r.responses_mentioned}` }],
    })));
    const byRate = s.slice().sort((a, b) => b.mention_rate_pct - a.mention_rate_pct);
    barChart($("chart-rate"), byRate.map((r) => ({
      label: r.destination, labelCls: r.group === "focus" ? "focus" : "",
      series: [{ value: r.mention_rate_pct, cls: r.group, text: pct(r.mention_rate_pct, 0),
        tip: `${r.destination}\nDisebut di ${r.responses_mentioned} dari ${h.responses_ok} jawaban (${pct(r.mention_rate_pct)})` }],
    })), 100);

    const langs = Array.from(new Set(res.by_language.map((r) => r.language)));
    langs.sort((a, b) => (a === "id" ? -1 : b === "id" ? 1 : cmp(a, b)));
    const lk = {}; for (const r of res.by_language) lk[r.language + "|" + r.destination_id] = r;
    barChart($("chart-lang"), s.map((d) => ({
      label: d.destination, labelCls: d.group === "focus" ? "focus" : "",
      series: langs.map((l) => {
        const r = lk[l + "|" + d.destination_id];
        const v = r ? r.share_of_voice_pct : 0;
        return { value: v, cls: "lang-" + l, text: pct(v), tip: `${d.destination}\n${LANG_LABELS[l] || l}: ${pct(v)} (${r ? r.mentions : 0} sebutan)` };
      }),
    })));

    const models = Array.from(new Set(res.by_model.map((r) => r.model_label))).sort();
    const mk = {}; for (const r of res.by_model) mk[r.model_label + "|" + r.destination_id] = r;
    const vmax = Math.max(1, ...res.by_model.map((r) => r.share_of_voice_pct));
    $("heat-model").innerHTML = `<thead><tr><th class="dest">Destinasi</th>${models.map((m) => `<th>${esc(m)}</th>`).join("")}</tr></thead><tbody>` +
      s.map((d) => `<tr><th class="dest">${esc(d.destination)}</th>${models.map((m) => {
        const r = mk[m + "|" + d.destination_id]; const v = r ? r.share_of_voice_pct : 0; const t = v / vmax;
        return `<td class="cell" style="background:${heatColor(t)};color:${t > 0.55 ? "#ffffff" : "#0b0b0b"}" data-tip="${esc(`${d.destination}\n${m}: ${pct(v)}`)}">${pct(v)}</td>`;
      }).join("")}</tr>`).join("") + "</tbody>";

    $("summary-table").innerHTML = `<thead><tr><th>#</th><th>Destinasi</th><th class="num">Sebutan</th><th class="num">Jawaban yang menyebut</th>
      <th class="num">Share of voice</th><th class="num">Mention rate</th><th class="num">Rata-rata urutan pertama</th></tr></thead><tbody>` +
      s.map((r) => `<tr class="${r.group}" data-dest="${r.destination_id}"><td>${r.rank}</td><td><i class="sw ${r.group}"></i> ${esc(r.destination)}</td>
        <td class="num">${r.mentions}</td><td class="num">${r.responses_mentioned}</td><td class="num">${pct(r.share_of_voice_pct)}</td>
        <td class="num">${pct(r.mention_rate_pct)}</td><td class="num">${r.avg_first_rank === null ? "" : r.avg_first_rank.toFixed(2)}</td></tr>`).join("") + "</tbody>";

    fillFilters();
    renderResponses();
  }

  function fillSelect(el, values, labeler) {
    const cur = el.value;
    el.innerHTML = `<option value="">(semua)</option>` + values.map((v) => `<option value="${esc(v)}">${esc(labeler ? labeler(v) : v)}</option>`).join("");
    if (values.includes(cur)) el.value = cur;
  }
  function fillFilters() {
    const recs = state.records;
    fillSelect($("f-model"), Array.from(new Set(recs.map((r) => r.model_label))).sort());
    fillSelect($("f-lang"), Array.from(new Set(recs.map((r) => r.language))).sort(), (l) => LANG_LABELS[l] || l);
    fillSelect($("f-dest"), state.config.destinations.map((d) => d.id), (id) => destName(state.config, id));
  }
  function renderResponses() {
    const cfg = state.config, matchers = buildMatchers(cfg.destinations);
    const fm = $("f-model").value, fl = $("f-lang").value, fd = $("f-dest").value;
    let list = state.records.filter((r) => (!fm || r.model_label === fm) && (!fl || r.language === fl));
    if (fd) list = list.filter((r) => r.status === "ok" && scanText(r.response, matchers)[fd][0] > 0);
    $("resp-count").textContent = `${list.length} jawaban${list.length > 30 ? " (30 pertama ditampilkan)" : ""}. Sorotan biru = fokus, oranye = kompetitor utama.`;
    $("responses").innerHTML = list.slice(0, 30).map((r) => {
      let body;
      if (r.status !== "ok") body = `<div class="err-text">${esc(r.error)}</div>`;
      else {
        const { norm, spans } = findSpans(r.response, matchers);
        let out = "", pos = 0;
        for (const [a, b, d] of spans) {
          out += esc(norm.slice(pos, a)) + `<mark class="${groupOf(cfg, d)}" title="${esc(destName(cfg, d))}">${esc(norm.slice(a, b))}</mark>`;
          pos = b;
        }
        body = `<pre>${out + esc(norm.slice(pos))}</pre>`;
      }
      return `<details><summary><b>${esc(r.model_label)}</b> | ${esc(r.question_id)}-${esc(r.language)} | ${esc(r.prompt)}</summary>${body}</details>`;
    }).join("");
  }

  // -------------------------------------------------------------------------
  // Sumber data
  // -------------------------------------------------------------------------
  function showError(msg) { const b = $("err-banner"); b.textContent = msg; b.classList.toggle("hidden", !msg); }
  function setData(records, source, cfg) {
    state.records = normalizeRecords(records);
    state.source = source;
    state.config = cfg || state.defaultConfig;
    showError("");
    render();
  }
  async function loadSample() {
    try {
      const r = await fetch("data/demo_results.json", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setData(data.responses, "contoh mode demo (data/demo_results.json)", data.config);
    } catch (e) {
      showError(`Gagal memuat contoh: ${e.message}. Buka halaman lewat GitHub Pages atau "python -m http.server" di folder docs.`);
    }
  }
  async function handleFile(file) {
    $("file-name").textContent = file.name;
    try {
      const text = await file.text();
      if (file.name.toLowerCase().endsWith(".json")) {
        const data = JSON.parse(text.replace(/^﻿/, ""));
        const recs = Array.isArray(data) ? data : data.responses;
        if (!Array.isArray(recs)) throw new Error("JSON tidak berisi daftar 'responses'");
        setData(recs, `file ${file.name}`, data.config && data.config.destinations ? data.config : null);
      } else {
        const recs = parseCSV(text);
        if (!recs.length || !("response" in recs[0])) throw new Error("CSV tidak punya kolom 'response'");
        setData(recs, `file ${file.name}`);
      }
    } catch (e) { showError(`File tidak bisa dibaca: ${e.message}`); }
  }

  // -------------------------------------------------------------------------
  // Audit langsung dari browser
  // -------------------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function postJSON(url, headers, body, signal) {
    for (let attempt = 0; ; attempt++) {
      let resp;
      try {
        resp = await fetch(url, { method: "POST", headers: Object.assign({ "content-type": "application/json" }, headers), body: JSON.stringify(body), signal });
      } catch (e) {
        if (signal && signal.aborted) throw e;
        if (attempt < 3) { await sleep(1000 * 2 ** attempt); continue; }
        throw new Error(`koneksi gagal (${e.message}); periksa CORS/jaringan`);
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

  async function callProvider(p, model, prompt, key, base, signal) {
    if (p === "anthropic") {
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
    if (p === "gemini") {
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

  function buildProviderGrid() {
    $("provider-grid").innerHTML = Object.entries(RUN_PROVIDERS).map(([p, info]) => `
      <div class="prov" data-p="${p}">
        <label class="chk"><input type="checkbox" class="p-on" ${p === "anthropic" || p === "gemini" ? "checked" : ""}> ${esc(info.label)}</label>
        <label>Model (pisahkan koma)<input type="text" class="p-model" value="${esc(info.model)}" placeholder="nama model"></label>
        ${info.customBase ? `<label>Base URL<input type="text" class="p-base" placeholder="https://api.groq.com/openai/v1"></label>` : ""}
        <label>${esc(info.keyName)}<input type="password" class="p-key" autocomplete="off" placeholder="tempel kunci API"></label>
      </div>`).join("");
  }

  async function runAudit() {
    const cfg = state.defaultConfig;
    const langs = $("run-langs").value.split(",");
    const maxq = Math.max(1, Math.min(cfg.questions.length, parseInt($("run-maxq").value, 10) || cfg.questions.length));
    const runs = Math.max(1, Math.min(5, parseInt($("run-runs").value, 10) || 1));
    const models = [];
    for (const el of document.querySelectorAll(".prov")) {
      if (!el.querySelector(".p-on").checked) continue;
      const p = el.dataset.p, info = RUN_PROVIDERS[p];
      const key = el.querySelector(".p-key").value.trim();
      const base = (info.customBase ? el.querySelector(".p-base").value.trim() : info.base).replace(/\/+$/, "");
      if (!key && p !== "custom") { showError(`Kunci API ${info.label} belum diisi.`); return; }
      if (info.customBase && !base) { showError("Base URL untuk provider OpenAI-compatible belum diisi."); return; }
      for (const m of el.querySelector(".p-model").value.split(",").map((x) => x.trim()).filter(Boolean)) models.push({ p, m, key, base });
    }
    if (!models.length) { showError("Pilih minimal satu provider dan model."); return; }
    showError("");
    const tasks = [];
    for (const md of models) for (const q of cfg.questions.slice(0, maxq)) for (const lang of langs) {
      const prompt = q.text[lang]; if (!prompt) continue;
      for (let run = 1; run <= runs; run++) {
        tasks.push({ md, rec: {
          response_id: `${md.p}:${md.m}|${q.qid}|${lang}|${run}`, provider: md.p, model: md.m, model_label: `${md.p}:${md.m}`,
          question_id: q.qid, category: q.category || "", language: lang, run, prompt,
        } });
      }
    }
    const ctrl = new AbortController(); state.abort = ctrl; state.running = true;
    $("run-btn").disabled = true; $("stop-btn").disabled = false; $("progress").classList.remove("hidden");
    const records = []; let done = 0, next = 0;
    const update = (last) => {
      $("progress-bar").style.width = `${(done / tasks.length * 100).toFixed(1)}%`;
      $("progress-text").textContent = `${done}/${tasks.length} permintaan ${last || ""}`;
    };
    update();
    const worker = async () => {
      while (next < tasks.length && !ctrl.signal.aborted) {
        const t = tasks[next++]; const rec = Object.assign({}, t.rec, { timestamp: new Date().toISOString().slice(0, 19), simulated: false });
        const t0 = performance.now();
        try {
          const r = await callProvider(t.md.p, t.md.m, rec.prompt, t.md.key, t.md.base, ctrl.signal);
          Object.assign(rec, { response: r.text, status: r.text.trim() ? "ok" : "error", error: r.text.trim() ? "" : "jawaban kosong",
            stop_reason: r.stop_reason ?? null, input_tokens: r.input_tokens ?? null, output_tokens: r.output_tokens ?? null });
        } catch (e) {
          Object.assign(rec, { response: "", status: "error", error: ctrl.signal.aborted ? "dihentikan" : String(e.message).slice(0, 500), stop_reason: null, input_tokens: null, output_tokens: null });
        }
        rec.latency_s = Math.round((performance.now() - t0) / 10) / 100;
        records.push(rec); done++;
        update(`| ${rec.model_label} ${rec.question_id}-${rec.language}: ${rec.status}`);
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    const order = Object.fromEntries(tasks.map((t, i) => [t.rec.response_id, i]));
    records.sort((a, b) => order[a.response_id] - order[b.response_id]);
    state.running = false; $("run-btn").disabled = false; $("stop-btn").disabled = true;
    const okN = records.filter((r) => r.status === "ok").length;
    if (records.length) setData(records, `audit di browser (${new Date().toLocaleString("id-ID")})`, cfg);
    if (!okN && records.length) showError(`Semua permintaan gagal. Contoh error: ${records[0].error}`);
  }

  // -------------------------------------------------------------------------
  // Unduhan & interaksi
  // -------------------------------------------------------------------------
  function download(name, content, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function wire() {
    for (const b of document.querySelectorAll(".seg-btn")) {
      b.addEventListener("click", () => {
        for (const x of document.querySelectorAll(".seg-btn")) { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", String(x === b)); }
        for (const body of document.querySelectorAll(".src-body")) body.classList.toggle("hidden", body.dataset.body !== b.dataset.src);
      });
    }
    $("load-sample").addEventListener("click", loadSample);
    $("file-input").addEventListener("change", (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });
    $("run-btn").addEventListener("click", runAudit);
    $("stop-btn").addEventListener("click", () => state.abort && state.abort.abort());
    for (const id of ["f-model", "f-lang", "f-dest"]) $(id).addEventListener("change", renderResponses);
    $("dl-responses").addEventListener("click", () => download("responses.csv", toCSV(state.records, RESPONSE_COLUMNS), "text/csv"));
    $("dl-summary").addEventListener("click", () => download("summary.csv", toCSV(state.results.summary,
      ["rank", "destination_id", "destination", "group", "mentions", "responses_mentioned", "share_of_voice_pct", "mention_rate_pct", "avg_first_rank"]), "text/csv"));
    $("dl-json").addEventListener("click", () => download("dashboard_data.json", JSON.stringify({
      meta: { tool: "GEM Visibility Auditor (web)", generated: new Date().toISOString() }, config: state.config,
      headline: state.results.headline, responses: state.records }, null, 1), "application/json"));
    const tip = $("tooltip");
    document.addEventListener("mousemove", (e) => {
      const t = e.target.closest && e.target.closest("[data-tip]");
      if (!t) { tip.classList.add("hidden"); return; }
      tip.textContent = t.dataset.tip; tip.classList.remove("hidden");
      const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = `${x}px`; tip.style.top = `${e.clientY + 14}px`;
    });
  }

  async function init() {
    wire();
    buildProviderGrid();
    try {
      const r = await fetch("data/config.json", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      state.defaultConfig = await r.json();
      state.config = state.defaultConfig;
    } catch (e) {
      showError(`Gagal memuat data/config.json: ${e.message}. Buka lewat GitHub Pages atau "python -m http.server" di folder docs.`);
      return;
    }
    await loadSample();
    document.body.dataset.ready = "1";
  }

  window.__gem = { state, analyze, parseCSV, buildMatchers, scanText, findSpans, toCSV, runAudit };
  init();
})();
