/* ══════════════════════════════════════════════════════════════════════
   Choice FinX Assist — POC chat frontend
   Consumes the HTTP/SSE contract:
     POST /session {userId, mobileNo, sessionToken, finxSessionId, clientCode}
                                                                -> {session_id}
     POST /chat    {session_id, messages, prior_cost_inr}        -> SSE
     POST /report  {session_id, report_type, params}   -> JSON ReportRenderPayload
   /chat SSE frames (event name = type): status | token | citations | usage |
   report_request | done | error.

   On a `report_request` frame the frontend chains the frame's declarative
   `steps` (card-select → date-range) into structured params, POSTs /report, and
   renders the returned ReportRenderPayload (table | link | empty | error)
   DIRECTLY — the model never touches report parameters or results.
   ══════════════════════════════════════════════════════════════════════ */

'use strict';

// ---------------------------------------------------------------------------
// Config & state
// ---------------------------------------------------------------------------

const API_BASE =
  new URLSearchParams(location.search).get('api') ||
  window.__API_BASE__ ||
  localStorage.getItem('finx_api_base') ||
  'http://localhost:8000';

// Human-readable titles per report_type, for the widget header and the durable
// history marker. Report parameter values themselves are opaque FinX tokens
// carried by the steps spec — never named here.
const REPORT_LABELS = {
  ledger: 'Ledger',
  global_pnl: 'Global P&L',
  detailed_pnl: 'Detailed P&L',
  contract_notes: 'Contract Notes',
  tax_report: 'Tax Report',
};

const SUGGESTIONS = [
  '📊 Show my ledger',
  '🧾 Get my contract notes',
  '💸 What are the brokerage charges?',
  '🔐 How do I reset my FinX password?',
];

const state = {
  session: null,        // {id, userId, mobileNo, clientCode}
  messages: [],         // durable Anthropic history — plain {role, content: string} turns
  cumulativeCost: 0,    // prior_cost_inr for the next call, from the last usage frame
  turns: 0,             // completed assistant turns (cost card)
  busy: false,          // a stream is in flight
};

// ---------------------------------------------------------------------------
// DOM handles
// ---------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const loginView = $('login-view');
const chatView = $('chat-view');
const messagesEl = $('messages');
const scrollRegion = $('scroll-region');
const inputEl = $('input');
const sendBtn = $('send-btn');

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Minimal, safe markdown-ish rendering: bold, inline code, bullets. */
function renderRich(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  html = html.replace(/^[-•] (.*)$/gm, '<span class="text-brand-500">•</span> $1');
  return html;
}

function fmtInr(value) {
  return value.toFixed(4);
}

function fmtLatency(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function nearBottom() {
  return scrollRegion.scrollHeight - scrollRegion.scrollTop - scrollRegion.clientHeight < 160;
}

function scrollToEnd(force = false) {
  if (force || nearBottom()) scrollRegion.scrollTo({ top: scrollRegion.scrollHeight });
}

// ---------------------------------------------------------------------------
// SSE over fetch: parse text/event-stream, dispatch on the event name
// ---------------------------------------------------------------------------

async function streamSSE(path, body, onFrame) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const err = await res.json();
      if (err.detail) detail = `${res.status} — ${JSON.stringify(err.detail)}`;
    } catch (_) { /* non-JSON error body */ }
    throw new Error(`request failed (${detail})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let eventName = null;
  let dataLines = [];

  const flush = () => {
    if (dataLines.length) {
      const raw = dataLines.join('\n');
      let payload = null;
      try { payload = JSON.parse(raw); } catch (_) { payload = raw; }
      onFrame(eventName || 'message', payload);
    }
    eventName = null;
    dataLines = [];
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      let line = buf.slice(0, nl);
      buf = buf.slice(nl + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);
      if (line === '') { flush(); continue; }        // blank line ends a frame
      if (line.startsWith(':')) continue;            // comment / keep-alive ping
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
      // id:/retry: fields are irrelevant for this POC
    }
  }
  flush();
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function removeEmptyState() {
  const empty = $('empty-state');
  if (empty) empty.remove();
}

function addUserMessage(text) {
  removeEmptyState();
  const row = document.createElement('div');
  row.className = 'flex justify-end msg-in';
  row.innerHTML = `
    <div class="bubble-user max-w-[85%] sm:max-w-[70%] px-4 py-2.5">
      <div class="msg-body"></div>
    </div>`;
  row.querySelector('.msg-body').textContent = text;
  messagesEl.appendChild(row);
  scrollToEnd(true);
}

/**
 * Create a streaming assistant bubble. Returns a handle used by the SSE
 * frame handlers: appendToken / setStatus / attachCitations / attachUsage /
 * finish / fail.
 */
function addAssistantMessage() {
  removeEmptyState();
  const row = document.createElement('div');
  row.className = 'flex justify-start msg-in';
  row.innerHTML = `
    <div class="max-w-[92%] sm:max-w-[80%] min-w-[8rem]">
      <div class="flex items-center gap-2 mb-1.5 pl-1">
        <div class="brand-tile w-6 h-6 rounded-lg flex items-center justify-center shrink-0">
          <span class="text-white text-[11px] font-display font-bold">✦</span>
        </div>
        <span class="status-line hidden"></span>
        <span class="typing-dots"><span></span><span></span><span></span></span>
      </div>
      <div class="bubble-ai streaming px-4 py-3 hidden">
        <div class="msg-body"></div>
      </div>
      <div class="meta-row mt-1.5 pl-1 flex flex-wrap items-center gap-1.5"></div>
    </div>`;
  messagesEl.appendChild(row);
  scrollToEnd(true);

  const bubble = row.querySelector('.bubble-ai');
  const body = row.querySelector('.msg-body');
  const statusEl = row.querySelector('.status-line');
  const dots = row.querySelector('.typing-dots');
  const metaRow = row.querySelector('.meta-row');
  let text = '';

  return {
    row,
    get text() { return text; },

    setStatus(message) {
      statusEl.textContent = message;
      statusEl.classList.remove('hidden');
      scrollToEnd();
    },

    appendToken(fragment) {
      text += fragment;
      bubble.classList.remove('hidden');
      body.innerHTML = renderRich(text);
      scrollToEnd();
    },

    attachCitations(citations) {
      if (!citations || !citations.length) return;
      metaRow.appendChild(buildCitationsChip(citations));
    },

    attachUsage(usage) {
      const pill = document.createElement('span');
      pill.className = 'meta-pill';
      pill.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-brand-400">
          <path fill-rule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm1-12a1 1 0 1 0-2 0v4c0 .27.1.52.3.7l2.8 2.8a1 1 0 0 0 1.4-1.4L11 9.58V6Z" clip-rule="evenodd"/>
        </svg>
        ₹${fmtInr(usage.cost_inr)} · ${fmtLatency(usage.latency_ms)}`;
      metaRow.appendChild(pill);
    },

    /**
     * Offer a one-tap resend after a failed turn. The failed user turn is
     * popped from durable history, so retrying re-runs sendMessage with the
     * same text — DOM and history can't silently diverge.
     */
    attachRetry(retryText) {
      if (!retryText) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'retry-btn';
      btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
          <path fill-rule="evenodd" d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z" clip-rule="evenodd"/>
        </svg>
        Try again`;
      btn.addEventListener('click', () => {
        btn.disabled = true;
        sendMessage(retryText);
      });
      metaRow.appendChild(btn);
      scrollToEnd();
    },

    /** Stop the streaming affordances (caret + dots + status). */
    settle() {
      bubble.classList.remove('streaming');
      dots.remove();
      statusEl.classList.add('hidden');
    },

    finish() {
      this.settle();
      if (!text) bubble.classList.add('hidden');
    },

    fail(message) {
      this.settle();
      bubble.classList.remove('hidden');
      bubble.classList.add('bubble-error');
      text = text ? `${text}\n\n⚠️ ${message}` : `⚠️ ${message}`;
      body.innerHTML = renderRich(text);
      scrollToEnd();
    },
  };
}

function buildCitationsChip(citations) {
  const wrap = document.createElement('span');
  wrap.className = 'cite-wrap';

  const items = citations
    .map((c) => {
      const title = c.question || c.section || c.topic || 'Knowledge-base entry';
      const crumbs = [c.topic, c.section].filter(Boolean).join(' › ');
      const src = [c.answer_source, c.source_sheet, c.source_row != null ? `row ${c.source_row}` : null]
        .filter(Boolean)
        .join(' · ');
      return `
        <div class="cite-item">
          <p class="text-[13px] font-semibold text-slate-100 leading-snug">${escapeHtml(title)}</p>
          ${crumbs ? `<p class="text-[12px] text-brand-300 mt-0.5">${escapeHtml(crumbs)}</p>` : ''}
          ${src ? `<p class="text-[11px] text-slate-400 mt-0.5">${escapeHtml(src)}</p>` : ''}
        </div>`;
    })
    .join('');

  wrap.innerHTML = `
    <button type="button" class="cite-chip" aria-expanded="false" aria-haspopup="true">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
        <path d="M7 3.5A1.5 1.5 0 0 1 8.5 2h3.879a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 17 6.622V12.5a1.5 1.5 0 0 1-1.5 1.5h-1v-3.379a3 3 0 0 0-.879-2.121L10.5 5.379A3 3 0 0 0 8.379 4.5H7v-1Z"/>
        <path d="M4.5 6A1.5 1.5 0 0 0 3 7.5v9A1.5 1.5 0 0 0 4.5 18h7a1.5 1.5 0 0 0 1.5-1.5v-5.879a1.5 1.5 0 0 0-.44-1.06L9.44 6.439A1.5 1.5 0 0 0 8.378 6H4.5Z"/>
      </svg>
      ${citations.length} source${citations.length > 1 ? 's' : ''}
    </button>
    <span class="cite-card">
      <p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400 mb-2">Grounded in the FinX knowledge base</p>
      ${items}
    </span>`;

  // Tap the button to toggle; click-outside and Escape close; clicks inside
  // the card don't bubble out to the outside-click handler. Hover reveal is
  // handled in CSS so the card stays hoverable AND tappable.
  const chipBtn = wrap.querySelector('.cite-chip');
  const cardEl = wrap.querySelector('.cite-card');
  const setOpen = (open) => {
    wrap.classList.toggle('open', open);
    chipBtn.setAttribute('aria-expanded', String(open));
  };
  chipBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    setOpen(!wrap.classList.contains('open'));
  });
  cardEl.addEventListener('click', (e) => e.stopPropagation());
  document.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setOpen(false);
  });
  return wrap;
}

// ---------------------------------------------------------------------------
// Cumulative cost card
// ---------------------------------------------------------------------------

function updateCostCard(cumulative) {
  const el = $('cost-total');
  const from = parseFloat(el.textContent) || 0;
  const to = cumulative;
  const t0 = performance.now();
  const dur = 600;
  (function tick(now) {
    const p = Math.min((now - t0) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = fmtInr(from + (to - from) * eased);
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
  $('cost-turns').textContent = String(state.turns);
  // playful "fuel gauge": fills toward ₹10 for the session
  $('cost-bar').style.width = `${Math.min((cumulative / 10) * 100, 100)}%`;
}

// ---------------------------------------------------------------------------
// Report widgets — chained declarative steps (structured params, never free
// text through the model). A report_request frame carries `steps`; each step is
// rendered in order, its choice accumulated into `params`, then POSTed to
// /report. A "Never mind" on any step cancels the whole chain.
// ---------------------------------------------------------------------------

// Resolved by a step when the user taps "Never mind".
const CANCEL = Symbol('cancel');

/** Shared widget-card header (brand tile + title + blurb). */
function widgetHeaderHtml(title, blurb) {
  return `
    <div class="flex items-center gap-2.5 mb-3.5">
      <div class="brand-tile w-8 h-8 rounded-xl flex items-center justify-center shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="white" class="w-4 h-4">
          <path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 0 0 3 3.5v13A1.5 1.5 0 0 0 4.5 18h11a1.5 1.5 0 0 0 1.5-1.5V7.62a1.5 1.5 0 0 0-.44-1.06l-4.12-4.12A1.5 1.5 0 0 0 11.38 2H4.5Zm2 8.75a.75.75 0 0 1 .75-.75h5.5a.75.75 0 0 1 0 1.5h-5.5a.75.75 0 0 1-.75-.75Zm.75 2.75a.75.75 0 0 0 0 1.5h5.5a.75.75 0 0 0 0-1.5h-5.5Z" clip-rule="evenodd"/>
        </svg>
      </div>
      <div>
        <p class="font-display font-semibold text-[15px] leading-tight text-slate-100">${escapeHtml(title)}</p>
        <p class="text-[12px] text-slate-400">${escapeHtml(blurb)}</p>
      </div>
    </div>`;
}

/** The "Never mind" cancel button (present on every step). */
function widgetCancelHtml() {
  return `
    <button type="button" data-cancel
            class="shrink-0 min-h-[44px] px-4 rounded-xl text-[13px] font-medium text-slate-400
                   border border-white/10 bg-white/5 hover:text-white hover:bg-white/10
                   transition-colors disabled:opacity-50">
      Never mind
    </button>`;
}

/**
 * Chain a report_request frame's `steps` in order, accumulate params, and
 * resolve the full param object — or `null` if any step is cancelled or an
 * unknown step kind is hit (forward-compat guard renders an error notice).
 */
async function renderReportSteps(steps, reportType) {
  const title = REPORT_LABELS[reportType] || reportType;
  const params = {};
  for (const step of steps) {
    let result;
    if (step.kind === 'cards') {
      result = await renderCardStep(step, title);
    } else if (step.kind === 'date_range') {
      result = await renderDateRangeStep(step, title);
    } else {
      renderNotice('error', title, `This report needs an app update to display (unknown step "${step.kind}").`);
      return null;
    }
    if (result === CANCEL) return null;
    Object.assign(params, result);
  }
  return params;
}

/** A `cards` step: one tappable card per option; resolves {[param]: value}. */
function renderCardStep(step, title) {
  return new Promise((resolve) => {
    removeEmptyState();
    const card = document.createElement('div');
    card.className = 'flex justify-start msg-in';
    const cardsHtml = (step.options || [])
      .map((o) => `
        <button type="button" data-value="${escapeHtml(o.value)}" class="report-choice">
          ${escapeHtml(o.label)}
        </button>`)
      .join('');
    card.innerHTML = `
      <div class="report-widget max-w-[92%] sm:max-w-[26rem] w-full p-5">
        ${widgetHeaderHtml(title, 'Pick an option to continue.')}
        <div class="report-choice-group">${cardsHtml}</div>
        <div class="mt-3.5">${widgetCancelHtml()}</div>
      </div>`;

    messagesEl.appendChild(card);
    scrollToEnd(true);

    const widget = card.querySelector('.report-widget');
    const lock = () => {
      widget.classList.add('done');
      for (const b of widget.querySelectorAll('button')) b.disabled = true;
    };
    for (const btn of widget.querySelectorAll('[data-value]')) {
      btn.addEventListener('click', () => {
        lock();
        btn.classList.add('selected');
        resolve({ [step.param]: btn.dataset.value });
      });
    }
    widget.querySelector('[data-cancel]').addEventListener('click', () => {
      lock();
      resolve(CANCEL);
    });
  });
}

/**
 * A `date_range` step: two native date inputs (already emit YYYY-MM-DD), no
 * defaults, submit gated until both are set and from ≤ to. Resolves
 * {[from_param]: from, [to_param]: to}.
 */
function renderDateRangeStep(step, title) {
  return new Promise((resolve) => {
    removeEmptyState();
    const card = document.createElement('div');
    card.className = 'flex justify-start msg-in';
    card.innerHTML = `
      <div class="report-widget max-w-[92%] sm:max-w-[26rem] w-full p-5">
        ${widgetHeaderHtml(title, 'Choose a date range.')}
        <form class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 mb-1">From</span>
              <input data-from type="date" required class="input-field !py-2.5" />
            </label>
            <label class="block">
              <span class="block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 mb-1">To</span>
              <input data-to type="date" required class="input-field !py-2.5" />
            </label>
          </div>
          <p data-daterr class="hidden text-[12px] text-rose-300">The “from” date must be on or before the “to” date.</p>
          <div class="flex gap-2 pt-0.5">
            ${widgetCancelHtml()}
            <button type="submit" data-submit disabled
                    class="btn-press btn-shine flex-1 min-h-[44px] rounded-xl font-display font-semibold text-white text-sm
                           bg-gradient-to-r from-brand-600 to-cyan-500 shadow-glow
                           transition-shadow duration-300 hover:shadow-lift
                           disabled:opacity-50 disabled:cursor-not-allowed">
              Continue →
            </button>
          </div>
        </form>
      </div>`;

    messagesEl.appendChild(card);
    scrollToEnd(true);

    const widget = card.querySelector('.report-widget');
    const form = widget.querySelector('form');
    const fromEl = form.querySelector('[data-from]');
    const toEl = form.querySelector('[data-to]');
    const errEl = form.querySelector('[data-daterr]');
    const submitBtn = form.querySelector('[data-submit]');

    // ISO YYYY-MM-DD strings compare correctly with a lexical <=.
    const validate = () => {
      const bothSet = Boolean(fromEl.value && toEl.value);
      const ordered = !bothSet || fromEl.value <= toEl.value;
      errEl.classList.toggle('hidden', !(bothSet && !ordered));
      submitBtn.disabled = !(bothSet && ordered);
    };
    fromEl.addEventListener('input', validate);
    toEl.addEventListener('input', validate);

    const lock = () => {
      widget.classList.add('done');
      for (const el of form.querySelectorAll('input, button')) el.disabled = true;
    };
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (!fromEl.value || !toEl.value || fromEl.value > toEl.value) return;
      lock();
      resolve({ [step.from_param]: fromEl.value, [step.to_param]: toEl.value });
    });
    form.querySelector('[data-cancel]').addEventListener('click', () => {
      lock();
      resolve(CANCEL);
    });
  });
}

// ---------------------------------------------------------------------------
// Report result rendering (ReportRenderPayload → DOM, no model involvement)
// ---------------------------------------------------------------------------

const MAX_TABLE_ROWS = 200;
const NUMERIC_RE = /^-?[₹$]?\s?[\d,]+(\.\d+)?%?$/;

/** Append a left-aligned assistant-side card wrapper; returns the inner node. */
function appendReportCard() {
  removeEmptyState();
  const row = document.createElement('div');
  row.className = 'flex justify-start msg-in';
  const inner = document.createElement('div');
  inner.className = 'max-w-[92%] sm:max-w-[80%] w-full';
  row.appendChild(inner);
  messagesEl.appendChild(row);
  scrollToEnd(true);
  return inner;
}

/** A transient "fetching…" card shown while POST /report is in flight. */
function appendLoadingCard(message) {
  removeEmptyState();
  const row = document.createElement('div');
  row.className = 'flex justify-start msg-in';
  row.innerHTML = `
    <div class="flex items-center gap-2 pl-1 py-1">
      <div class="brand-tile w-6 h-6 rounded-lg flex items-center justify-center shrink-0">
        <span class="text-white text-[11px] font-display font-bold">✦</span>
      </div>
      <span class="status-line"></span>
      <span class="typing-dots"><span></span><span></span><span></span></span>
    </div>`;
  row.querySelector('.status-line').textContent = message;
  messagesEl.appendChild(row);
  scrollToEnd(true);
  return row;
}

function isNumericish(v) {
  if (typeof v === 'number') return true;
  if (typeof v !== 'string') return false;
  const s = v.trim();
  return s !== '' && NUMERIC_RE.test(s);
}

/** Render a ReportRenderPayload directly (table | link | empty | error). */
function renderReportPayload(payload) {
  const title = payload.title || 'Report';
  switch (payload.kind) {
    case 'table':
      renderTable(payload, title);
      break;
    case 'link':
      renderLink(payload, title);
      break;
    case 'empty':
      renderNotice('empty', title, payload.message || 'No data for this report.');
      break;
    case 'error':
      renderNotice('error', title, payload.message || 'This report could not be generated.');
      break;
    default:
      renderNotice('error', title, `Unsupported report result (kind "${payload.kind}").`);
  }
}

/** Horizontally scrollable table with numeric right-align and a row cap. */
function renderTable(payload, title) {
  const inner = appendReportCard();
  const columns = payload.columns || [];
  const allRows = payload.rows || [];
  const rows = allRows.slice(0, MAX_TABLE_ROWS);

  const head = columns
    .map((c) => `<th class="report-th">${escapeHtml(c.label)}</th>`)
    .join('');

  const body = rows
    .map((r) => {
      const cells = columns
        .map((c) => {
          const raw = r[c.key];
          const val = raw == null ? '' : String(raw);
          const cls = isNumericish(raw) ? 'report-td report-td-num' : 'report-td';
          return `<td class="${cls}">${escapeHtml(val)}</td>`;
        })
        .join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');

  const capped = allRows.length > rows.length
    ? `<p class="report-note">Showing ${rows.length} of ${allRows.length} rows.</p>`
    : '';

  inner.innerHTML = `
    <div class="report-result">
      <p class="report-result-title">${escapeHtml(title)}</p>
      <div class="overflow-x-auto report-table-scroll">
        <table class="report-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${capped}
    </div>`;
  scrollToEnd(true);
}

/**
 * Download card for a `link` payload. The URL is unauthenticated/sensitive: it
 * rides ONLY in the anchor href (built via DOM, opened in a new tab with
 * rel="noopener"), never copied into chat text or durable history.
 */
function renderLink(payload, title) {
  const inner = appendReportCard();
  const wrap = document.createElement('div');
  wrap.className = 'report-result';

  const a = document.createElement('a');
  a.href = payload.url || '#';
  a.target = '_blank';
  a.rel = 'noopener';
  a.className = 'download-card';
  a.innerHTML = `
    <span class="download-icon" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
        <path d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.19L6.28 8.22a.75.75 0 0 0-1.06 1.06l3.75 3.75a.75.75 0 0 0 1.06 0l3.75-3.75a.75.75 0 1 0-1.06-1.06l-2.97 2.72V2.75Z"/>
        <path d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"/>
      </svg>
    </span>
    <span class="download-text">
      <span class="download-title"></span>
      <span class="download-sub"></span>
    </span>
    <span class="download-cta">Open →</span>`;
  a.querySelector('.download-title').textContent = title;
  a.querySelector('.download-sub').textContent = payload.message || 'Opens the report in a new tab';

  wrap.appendChild(a);
  inner.appendChild(wrap);
  scrollToEnd(true);
}

/** Informational notice for empty/error payloads (and the unknown-kind guard). */
function renderNotice(kind, title, message) {
  const inner = appendReportCard();
  const isErr = kind === 'error';
  inner.innerHTML = `
    <div class="report-notice ${isErr ? 'report-notice-error' : ''}">
      <p class="report-result-title">${escapeHtml(title)}</p>
      <p class="text-[13px] text-slate-300 mt-0.5">${escapeHtml(message)}</p>
    </div>`;
  scrollToEnd(true);
}

// ---------------------------------------------------------------------------
// Chat orchestration: one turn = /chat stream, optionally paused by a
// report_request and resumed via /report
// ---------------------------------------------------------------------------

function setBusy(busy) {
  state.busy = busy;
  // Gate only the send button — disabling the textarea would dismiss the iOS
  // keyboard on every turn. sendMessage() early-returns while busy, so Enter
  // can't double-submit.
  sendBtn.disabled = busy || !inputEl.value.trim();
  if (!busy) inputEl.focus();
}

/**
 * Consume one /chat SSE stream into an assistant bubble. Resolves
 * {report, text, errored, dropped}:
 *   report  — {reportType, steps} if a report_request frame arrived, else null
 *   errored — an `error` frame arrived, OR the stream closed with no terminal
 *             frame at all (a dropped connection is treated as a failed turn)
 *   dropped — the stream closed without done/error/report_request
 */
function consumeStream(path, body, bubble) {
  return new Promise((resolve, reject) => {
    let report = null;
    let errored = false;
    let sawDone = false;
    streamSSE(path, body, (event, data) => {
      switch (event) {
        case 'status':
          bubble.setStatus(data.message);
          break;
        case 'token':
          bubble.appendToken(data.text);
          break;
        case 'citations':
          bubble.attachCitations(data.citations);
          break;
        case 'usage':
          state.cumulativeCost = data.usage.cumulative_cost_inr;
          state.turns += 1;
          bubble.attachUsage(data.usage);
          updateCostCard(state.cumulativeCost);
          break;
        case 'report_request':
          report = { reportType: data.report_type, steps: data.steps || [] };
          break;
        case 'done':
          sawDone = true;
          break;
        case 'error':
          errored = true;
          bubble.fail(data.message || 'Something went wrong.');
          break;
      }
    }).then(() => {
      const dropped = !sawDone && !report && !errored;
      resolve({ report, text: bubble.text, errored: errored || dropped, dropped });
    }, reject);
  });
}

/**
 * CHO-61 — the single stream-teardown site for a /chat stream. Whatever the
 * terminal condition (done, error, a report_request turn end, an exception, or
 * the stream closing with no terminal frame), this always stops the "Generating
 * answer…" affordances so no path can leave the indicator spinning.
 */
function finalizeMessage(bubble, outcome) {
  if (outcome.failMessage) {          // exception path — render the failure now
    bubble.fail(outcome.failMessage);
  } else if (outcome.dropped) {       // stream closed with no terminal frame
    bubble.fail('The connection closed unexpectedly — please try again.');
  } else if (outcome.errored) {       // error frame already rendered via fail()
    bubble.settle();
  } else {                            // done, or a report_request turn end
    bubble.finish();
  }
}

async function sendMessage(rawText) {
  const text = rawText.trim();
  if (!text || state.busy || !state.session) return;

  setBusy(true);
  inputEl.value = '';
  inputEl.style.height = 'auto';
  addUserMessage(text);
  state.messages.push({ role: 'user', content: text });

  const bubble = addAssistantMessage();
  let outcome;
  try {
    outcome = await consumeStream(
      '/chat',
      {
        session_id: state.session.id,
        messages: state.messages,
        prior_cost_inr: state.cumulativeCost,
      },
      bubble,
    );
  } catch (err) {
    outcome = { report: null, text: bubble.text, errored: true, dropped: false,
                failMessage: err.message || 'Network error — is the backend running?' };
  }

  // Terminal handling happens here and only here (CHO-61).
  finalizeMessage(bubble, outcome);

  try {
    if (outcome.report) {
      // The turn ends at the report_request; any preamble text the model
      // streamed becomes a durable assistant turn, then the widget chain runs.
      if (outcome.text) state.messages.push({ role: 'assistant', content: outcome.text });
      await runReportFlow(outcome.report);
    } else if (outcome.errored) {
      state.messages.pop(); // failed turn: drop the user msg so history stays clean
      bubble.attachRetry(text);
    } else {
      state.messages.push({ role: 'assistant', content: outcome.text });
    }
  } finally {
    setBusy(false);
  }
}

/**
 * Drive a report_request to completion: chain its widget steps into structured
 * params, POST /report, and render the returned ReportRenderPayload directly —
 * no model round-trip. Durable history gains only a plain-text `[<title>
 * displayed]` marker (never raw report data or the sensitive URL).
 */
async function runReportFlow(report) {
  const { reportType, steps } = report;
  const title = REPORT_LABELS[reportType] || reportType;

  const params = await renderReportSteps(steps, reportType);
  if (params === null) return; // cancelled — nothing posted

  const loader = appendLoadingCard('Fetching your report from FinX…');
  try {
    const res = await fetch(`${API_BASE}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.session.id, report_type: reportType, params }),
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try {
        const err = await res.json();
        if (err.detail) detail = `${res.status} — ${JSON.stringify(err.detail)}`;
      } catch (_) { /* non-JSON error body */ }
      throw new Error(`report request failed (${detail})`);
    }
    const payload = await res.json();
    loader.remove();
    renderReportPayload(payload);
    state.messages.push({ role: 'assistant', content: historyMarker(payload, title) });
  } catch (err) {
    loader.remove();
    renderNotice('error', title, err.message || 'Report request failed.');
  }
}

/** Plain-text durable-history marker for a rendered report — never raw data/URL. */
function historyMarker(payload, fallbackTitle) {
  const title = payload.title || fallbackTitle;
  if (payload.kind === 'empty') return `[${title}: no data]`;
  if (payload.kind === 'error') return `[${title}: unavailable]`;
  return `[${title} displayed]`;
}

// ---------------------------------------------------------------------------
// Login / logout
// ---------------------------------------------------------------------------

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('login-btn');
  const errEl = $('login-error');
  errEl.classList.add('hidden');

  // spec: trim ALL five inputs before POST /session
  const mobileNo = $('login-phone').value.trim();
  const userId = $('login-userid').value.trim();
  const sessionToken = $('login-token').value.trim();
  const finxSessionId = $('login-finx').value.trim();
  const clientCode = $('login-clientcode').value.trim();

  // Inline required-field validation — FinX Session ID and client code are the
  // two new mandatory identity fields; block submission and send nothing if any
  // required value is empty (mirrors the server's non-empty checks).
  if (!mobileNo || !userId || !sessionToken || !finxSessionId || !clientCode) {
    errEl.textContent = 'All fields are required — including FinX Session ID and client code.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Warming up…';
  try {
    const res = await fetch(`${API_BASE}/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        userId,
        mobileNo,
        sessionToken,
        finxSessionId,
        clientCode,
      }),
    });
    if (!res.ok) throw new Error(`login failed (${res.status})`);
    const data = await res.json();

    state.session = { id: data.session_id, userId, mobileNo, clientCode, finxSessionId };
    state.messages = [];
    state.cumulativeCost = 0;
    state.turns = 0;

    $('header-user').textContent = userId;
    $('empty-name').textContent = userId;
    loginView.classList.add('hidden');
    chatView.classList.remove('hidden');
    updateCostCard(0);
    inputEl.focus();
  } catch (err) {
    errEl.textContent = `${err.message} — check the token & that the API is up at ${API_BASE}`;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Enter the chat →';
  }
});

$('logout-btn').addEventListener('click', () => location.reload());

// ---------------------------------------------------------------------------
// Composer wiring
// ---------------------------------------------------------------------------

$('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  sendMessage(inputEl.value);
});

inputEl.addEventListener('input', () => {
  sendBtn.disabled = state.busy || !inputEl.value.trim();
  inputEl.style.height = 'auto';
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 160)}px`;
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

// suggestion chips
const suggestionsEl = $('suggestions');
for (const suggestion of SUGGESTIONS) {
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'chip';
  chip.textContent = suggestion;
  chip.addEventListener('click', () => {
    // strip the leading emoji before sending
    sendMessage(suggestion.replace(/^\p{Emoji_Presentation}\s*/u, ''));
  });
  suggestionsEl.appendChild(chip);
}
