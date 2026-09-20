/**
 * HealthAI Lite — Frontend Core
 * Works with a live FastAPI backend OR in standalone demo mode (no server needed).
 */

// When served from the FastAPI server at localhost:8000/ui/, API is at same origin
// When opened as file://, we try localhost:8000 and fall back to demo mode
const _isServedFromBackend =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1";

const API_BASE = _isServedFromBackend ? "" : "http://localhost:8000";


// ─── Auth ────────────────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem("healthai_token"); }
function getUser()  { return localStorage.getItem("healthai_user") || "admin"; }

function setToken(token, username) {
  localStorage.setItem("healthai_token", token);
  localStorage.setItem("healthai_user", username || "");
}

function logout() {
  localStorage.removeItem("healthai_token");
  localStorage.removeItem("healthai_user");
  window.location.href = "index.html";
}

function requireAuth() {
  if (!getToken()) window.location.href = "index.html";
}

// ─── Mock data store (IndexedDB-backed via localStorage) ─────────────────────
const MOCK = (() => {
  const KEY_DS  = "hai_datasets";
  const KEY_QS  = "hai_queries";

  function load(key)         { try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch { return []; } }
  function save(key, data)   { localStorage.setItem(key, JSON.stringify(data)); }

  function datasets()        { return load(KEY_DS); }
  function queries()         { return load(KEY_QS); }

  function addDataset(ds)    { const list = datasets(); list.unshift(ds); save(KEY_DS, list); }
  function addQuery(q)       { const list = queries();  list.unshift(q);  save(KEY_QS, list.slice(0,50)); }

  // ── Evaluation matrix (mirrors backend/evaluator.py) ──
  const STOPWORDS = new Set(["the","a","an","is","are","was","were","of","to","in","on","for","and","or","it","this","that","with","as","by","be","what","how","why","does","do","did","can","you","your","i"]);
  const UNSAFE = ["kill","bomb","weapon","hack password","suicide","self-harm"];

  function tokens(text) {
    return new Set((text.toLowerCase().match(/[a-z0-9']+/g) || []).filter(w => !STOPWORDS.has(w) && w.length > 2));
  }
  function intersection(a, b) { return new Set([...a].filter(x => b.has(x))); }

  function relevance(q, a) {
    const qt = tokens(q), at = tokens(a);
    if (!qt.size || !at.size) return 0;
    const score = intersection(qt, at).size / Math.max(1, qt.size) * 100;
    return Math.min(100, +(score * 1.6).toFixed(1));
  }

  function groundedness(a, ctx) {
    if (!ctx) return 100;
    const at = tokens(a), ct = tokens(ctx);
    if (!at.size) return 0;
    return Math.min(100, +(intersection(at, ct).size / Math.max(1, at.size) * 100).toFixed(1));
  }

  function coherence(a) {
    const words = a.split(/\s+/).filter(Boolean);
    const n = words.length;
    if (n === 0) return 0;
    if (n < 6)   return 40;
    if (n > 400) return 70;
    const sents = a.split(/[.!?]+/).filter(s => s.trim());
    const avgLen = n / Math.max(1, sents.length);
    return Math.max(30, Math.min(100, +(100 - Math.abs(avgLen - 16) * 1.5).toFixed(1)));
  }

  function safety(a) {
    const low = a.toLowerCase();
    const hits = UNSAFE.filter(m => low.includes(m)).length;
    return hits === 0 ? 100 : Math.max(0, 100 - hits * 40);
  }

  function evaluate(question, answer, ctx) {
    const r = relevance(question, answer);
    const g = groundedness(answer, ctx);
    const c = coherence(answer);
    const s = safety(answer);
    const q = +(r*0.35 + g*0.25 + c*0.25 + s*0.15).toFixed(1);
    const st = v => v >= 75 ? "good" : v >= 50 ? "warn" : "poor";
    return {
      relevance: r, groundedness: g, coherence: c, safety: s,
      quality_score: q,
      status: { relevance: st(r), groundedness: st(g), coherence: st(c), safety: st(s), quality_score: st(q) }
    };
  }

  // ── Mock answer generator ──
  const HEALTH_KB = {
    "diabetes": "Diabetes mellitus is a chronic metabolic disorder characterised by persistent hyperglycaemia. Key clinical indicators include:\n• HbA1c — primary long-term control marker; target <7.0% (53 mmol/mol) for most adults.\n• Fasting plasma glucose — normal <5.6 mmol/L; diabetes diagnosed at ≥7.0 mmol/L.\n• 2-hour post-load glucose — diabetes at ≥11.1 mmol/L on OGTT.\n• eGFR and urine albumin/creatinine ratio — screened annually for diabetic nephropathy.\n• Blood pressure target: <130/80 mmHg to reduce cardiovascular risk.\n• LDL cholesterol target: <1.8 mmol/L (70 mg/dL) in high-risk patients.\nManagement: metformin first-line, GLP-1 agonists, SGLT2 inhibitors, dietary modification (low GI, fibre-rich), ≥150 min/week moderate aerobic exercise.",
    "blood pressure": "Hypertension classification (ACC/AHA 2017):\n• Normal: <120/80 mmHg\n• Elevated: 120–129/<80 mmHg\n• Stage 1: 130–139/80–89 mmHg\n• Stage 2: ≥140/≥90 mmHg\n• Hypertensive crisis: >180/>120 mmHg (immediate evaluation required)\nFirst-line drugs: thiazide diuretics, ACE inhibitors/ARBs, calcium channel blockers. Lifestyle: DASH diet (sodium <2.3 g/day), aerobic exercise, weight reduction can reduce systolic BP by 4–11 mmHg.",
    "cholesterol": "Lipid panel targets:\n• LDL-C: optimal <2.6 mmol/L (<100 mg/dL); <1.8 mmol/L (<70 mg/dL) for very-high-risk patients.\n• HDL-C: cardioprotective at >1.0 mmol/L (men), >1.3 mmol/L (women).\n• Triglycerides: normal <1.7 mmol/L (<150 mmol/L / <150 mg/dL).\n• Non-HDL-C and ApoB are secondary targets in metabolic syndrome.\nStatins reduce LDL by 30–50%. Ezetimibe and PCSK9 inhibitors provide additive lowering. Dietary saturated fat <7% of total energy.",
    "bmi": "BMI (weight kg ÷ height m²) classification:\n• Underweight: <18.5\n• Normal: 18.5–24.9\n• Overweight: 25.0–29.9\n• Class I obesity: 30.0–34.9\n• Class II: 35.0–39.9\n• Class III: ≥40.0\nLimitation: does not distinguish fat from lean mass. Waist circumference (>88 cm women, >102 cm men) and waist-to-hip ratio add metabolic risk context. South Asian intervention threshold is often 23 kg/m².",
    "heart": "Cardiovascular risk markers:\n• Resting HR: 60–100 bpm normal; bradycardia <60 / tachycardia >100 require evaluation.\n• LVEF: normal ≥55%; HFrEF defined as LVEF <40%.\n• BNP/NT-proBNP: elevated in heart failure and volume overload.\n• Troponin I/T: gold standard for myocardial injury.\n• 10-year ASCVD risk: low <5%, borderline 5–7.5%, intermediate 7.5–20%, high ≥20%.\nPrimary prevention targets: LDL-C, BP, HbA1c, smoking cessation, ≥150 min/week activity.",
    "kidney": "CKD staging (eGFR mL/min/1.73m²):\n• G1: ≥90 (with markers of damage)\n• G2: 60–89\n• G3a: 45–59 / G3b: 30–44\n• G4: 15–29\n• G5: <15 (kidney failure)\nKey markers: serum creatinine, cystatin C, urine ACR (≥30 mg/g significant). ACE-I/ARBs are nephroprotective. SGLT2 inhibitors (empagliflozin, dapagliflozin) reduce CKD progression.",
    "patient": "Patient clinical profiling typically covers:\n• Demographics: age, sex, BMI, smoking status, alcohol use.\n• Vital signs: BP, HR, respiratory rate, SpO2, temperature.\n• Laboratory: CBC, metabolic panel (glucose, creatinine, electrolytes), lipid panel, HbA1c, LFTs.\n• Comorbidities: hypertension, diabetes, dyslipidaemia, CKD, cardiovascular disease.\n• Medications: current prescriptions, OTC drugs, allergies.\nStructured problem lists and longitudinal trending of key biomarkers enable pattern recognition and early intervention.",
  };

  function mockAnswer(question, ctx) {
    const q = question.toLowerCase();
    for (const [keyword, answer] of Object.entries(HEALTH_KB)) {
      if (q.includes(keyword)) {
        if (ctx) return answer + "\n\n— Dataset context was considered. Add an OPENAI_API_KEY to backend/.env for a fully context-aware live response.";
        return answer + "\n\n(Demo mode — add OPENAI_API_KEY to backend/.env for live, personalised AI responses.)";
      }
    }
    // Generic structured fallback
    const title = question.trim().replace(/\?$/, "");
    if (ctx) return `Context-aware analysis of "${title}":\n\nThe uploaded dataset records show variable patterns across the measured parameters. Recommended analytical steps:\n1. Identify outliers beyond ±2 SD from the cohort mean.\n2. Check temporal trends for improvement or deterioration signals.\n3. Cross-reference flagged values with NICE/WHO clinical reference ranges.\n4. Correlate co-morbidity flags with primary outcome metrics.\n\nFor a live, evidence-based answer grounded in your data, add OPENAI_API_KEY to backend/.env. (Demo mode)`;
    return `General clinical response to "${title}":\n\nThis question relates to health monitoring, diagnostic criteria, and evidence-based clinical practice. Standard guidelines from WHO, CDC, NICE, and AHA/ACC provide reference ranges and intervention thresholds.\n\nFor a precise, data-specific answer, upload a relevant dataset and re-run with dataset context selected, or connect a live AI model via OPENAI_API_KEY in backend/.env.\n\n(Demo mode — running without a live AI model.)`;
  }

  return { datasets, queries, addDataset, addQuery, evaluate, mockAnswer };
})();

// ─── API wrapper (tries live backend, falls back to mock) ─────────────────────
let _backendAvailable = _isServedFromBackend ? true : null; // true if served from FastAPI

async function checkBackend() {
  if (_backendAvailable !== null) return _backendAvailable;
  try {
    const r = await fetch(`http://localhost:8000/api/health`, { signal: AbortSignal.timeout(2000) });
    _backendAvailable = r.ok;
  } catch {
    _backendAvailable = false;
  }
  return _backendAvailable;
}

async function api(path, options = {}) {
  const live = await checkBackend();

  if (live) {
    // ── Live backend path ──────────────────────────────────────────────
    const headers = options.headers || {};
    if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401) { logout(); throw new Error("Session expired"); }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res.json();
  }

  // ── Demo/mock backend path ───────────────────────────────────────────
  return mockApi(path, options);
}

async function mockApi(path, options = {}) {
  await new Promise(r => setTimeout(r, 180)); // simulate network

  // Auth
  if (path === "/api/auth/login" && options.method === "POST") {
    const body = JSON.parse(options.body);
    if (body.username === "admin" && body.password === "admin123") {
      return { token: "demo-token-" + Date.now(), username: "admin" };
    }
    throw new Error("Invalid username or password");
  }
  if (path === "/api/auth/me") return { username: getUser() };

  // Datasets
  if (path === "/api/ingest/datasets") return MOCK.datasets();
  if (path === "/api/ingest/upload" && options.method === "POST") {
    const form = options.body;
    const file = form.get("file");
    const now = Date.now() / 1000;
    const ext = file.name.split('.').pop().toLowerCase();
    const kind = ext === "csv" ? "csv" : ext === "pdf" ? "pdf" : "text";
    let rowCount = 0, columns = [], sample = [], textPreview = "";
    if (kind === "csv") {
      const text = await file.text();
      const rows = text.split("\n").filter(Boolean);
      columns = (rows[0] || "").split(",").map(c => c.trim());
      rowCount = Math.max(0, rows.length - 1);
      sample = rows.slice(1, 6).map(r => r.split(","));
    } else {
      const text = await file.text().catch(() => "");
      rowCount = text.split("\n").length;
      textPreview = text.slice(0, 2000);
    }
    const ds = {
      id: Date.now(), filename: file.name, kind, row_count: rowCount,
      columns_json: JSON.stringify(columns),
      sample_json: JSON.stringify(sample),
      text_preview: textPreview, uploaded_at: now
    };
    MOCK.addDataset(ds);
    return ds;
  }

  // Query
  if (path === "/api/query" && options.method === "POST") {
    const body = JSON.parse(options.body);
    const start = Date.now();
    let ctx = null;
    if (body.dataset_id) {
      const ds = MOCK.datasets().find(d => d.id == body.dataset_id);
      if (ds) {
        if (ds.text_preview) ctx = ds.text_preview;
        else {
          try { ctx = `Columns: ${JSON.parse(ds.columns_json)}\nSample: ${JSON.parse(ds.sample_json)}`; } catch {}
        }
      }
    }
    await new Promise(r => setTimeout(r, 400 + Math.random() * 600));
    const answer = MOCK.mockAnswer(body.question, ctx);
    const latency_ms = Date.now() - start;
    const tokens_est = Math.max(1, Math.round(answer.split(" ").length * 1.3));
    const metrics = MOCK.evaluate(body.question, answer, ctx);
    const q = {
      id: Date.now(), question: body.question, answer,
      dataset_id: body.dataset_id || null, mocked: 1,
      ...metrics, latency_ms, tokens_est, created_at: Date.now() / 1000
    };
    MOCK.addQuery(q);
    return { question: body.question, answer, mocked: true, latency_ms, tokens_est, matrix: metrics };
  }

  if (path === "/api/query/history") return MOCK.queries();

  // Dashboard stats
  if (path === "/api/dashboard/stats") {
    const datasets = MOCK.datasets();
    const queries = MOCK.queries();
    const totalRows = datasets.reduce((s, d) => s + (d.row_count || 0), 0);
    const avgQuality = queries.length ? queries.reduce((s, q) => s + (q.quality_score||0), 0) / queries.length : 0;
    const avgLatency = queries.length ? queries.reduce((s, q) => s + (q.latency_ms||0), 0) / queries.length : 0;
    const trend = queries.slice(0, 15).reverse().map((q, i) => ({ id: q.id, quality_score: q.quality_score, latency_ms: q.latency_ms, created_at: q.created_at }));
    const recent = queries.slice(0, 8);
    return {
      datasets_count: datasets.length, total_rows: totalRows,
      queries_count: queries.length, avg_quality: +avgQuality.toFixed(1),
      avg_latency_ms: +avgLatency.toFixed(1), trend, recent_queries: recent
    };
  }

  throw new Error("Not found: " + path);
}

// ─── Nav ──────────────────────────────────────────────────────────────────────
function renderNav(active) {
  const items = [
    ["dashboard.html", "Dashboard", "📊"],
    ["query.html", "AI Query", "🤖"],
    ["ingest.html", "Data Ingestion", "📁"],
  ];
  const user = getUser();
  return `
    <div class="sidebar">
      <div class="brand">
        <div class="brand-icon">🧬</div>
        <div class="brand-text">
          <span>HealthAI Lite</span>
          <span>Evaluation Platform</span>
        </div>
      </div>
      <div class="nav-section-label">Navigation</div>
      ${items.map(([href, label, icon]) =>
        `<a class="nav-item ${active === href ? "active" : ""}" href="${href}">
          <span class="nav-icon">${icon}</span> ${label}
        </a>`
      ).join("")}
      <div class="sidebar-footer">
        <div id="mode-badge" style="
          margin-bottom:0.625rem;
          padding:0.5rem 0.75rem;
          border-radius:8px;
          font-size:0.68rem;
          font-weight:600;
          letter-spacing:0.04em;
          text-transform:uppercase;
          background:rgba(245,158,11,0.10);
          color:#f59e0b;
          border:1px solid rgba(245,158,11,0.2);
          display:flex;align-items:center;gap:0.4rem;
        ">
          <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#f59e0b;animation:modepulse 2s ease-in-out infinite"></span>
          <span id="mode-label">Checking…</span>
        </div>
        <div class="logout" onclick="logout()">
          <span>⎋</span>
          <span>Sign out (${user})</span>
        </div>
      </div>
    </div>
  `;
}

// Update mode badge after nav renders
function updateModeBadge() {
  checkBackend().then(live => {
    const badge = document.getElementById("mode-badge");
    const label = document.getElementById("mode-label");
    if (!badge || !label) return;
    if (live) {
      badge.style.background = "rgba(16,185,129,0.10)";
      badge.style.color = "#10b981";
      badge.style.borderColor = "rgba(16,185,129,0.2)";
      badge.querySelector("span").style.background = "#10b981";
      label.textContent = "Live Backend";
    } else {
      label.textContent = "Demo Mode";
    }
  });
}
setTimeout(updateModeBadge, 100);

// ─── Helpers ──────────────────────────────────────────────────────────────────
function statusFor(v) { return v >= 75 ? "good" : v >= 50 ? "warn" : "poor"; }
function statusIcon(v) { return v >= 75 ? "✓" : v >= 50 ? "!" : "✗"; }

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const diff = Date.now() - d.getTime();
  if (diff < 60000)    return "just now";
  if (diff < 3600000)  return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return d.toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function animateNumber(el, target, duration = 900, decimals = 0) {
  const start = parseFloat(el.textContent) || 0;
  const t0 = performance.now();
  const step = now => {
    const p = Math.min((now - t0) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    const cur = start + (target - start) * ease;
    el.textContent = decimals > 0 ? cur.toFixed(decimals) : Math.round(cur).toLocaleString();
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
