/* ══════════════════════════════════════════════════════════════════════
   Choice FinX Assist — POC chat frontend
   Consumes the P5 HTTP/SSE contract:
     POST /session {userId, mobileNo, sessionToken, clientCode?} -> {session_id}
     POST /chat    {session_id, messages, prior_cost_inr}        -> SSE
     POST /report  {session_id, report_type, params, tool_use_id,
                    messages, prior_cost_inr}                    -> SSE
   SSE frames (event name = type): status | token | citations | usage |
   report_request | done | error.

   Report params are ONLY ever collected via the structured widget below —
   never as free text routed through the model.
   ══════════════════════════════════════════════════════════════════════ */

'use strict';

// ---------------------------------------------------------------------------
// Config & state
// ---------------------------------------------------------------------------

const API_BASE =
  new URLSearchParams(location.search).get('api') ||
  localStorage.getItem('finx_api_base') ||
  'http://localhost:8000';

// Report tool names as registered with the Anthropic API (backend/agent/tools.py).
// Needed to synthesize the paused assistant tool_use block for /report resume.
const REPORT_TOOL_NAMES = { cml: 'cml_report', contract_note: 'contract_note' };

const FIELD_META = {
  client_id: { label: 'Client ID', type: 'text', placeholder: 'e.g. X001234' },
  mobile_no: { label: 'Mobile number', type: 'tel', placeholder: '10-digit mobile' },
  contract_date: { label: 'Contract date', type: 'date', placeholder: '' },
};

const SUGGESTIONS = [
  '📄 Get my CML report',
  '🧾 Show my contract note',
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

/** yyyy-mm-dd (native date input) -> DD-MM-YYYY (FinX contract-note format). */
function toDdMmYyyy(isoDate) {
  const [y, m, d] = isoDate.split('-');
  return `${d}-${m}-${y}`;
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
// Report widget (structured params — never free text through the model)
// ---------------------------------------------------------------------------

const REPORT_TITLES = {
  cml: { title: 'CML report', blurb: 'Client Master List — straight from FinX.' },
  contract_note: { title: 'Contract note', blurb: 'Pick the trade date — we fetch the note.' },
};

function prefillFor(field) {
  if (field === 'mobile_no') return state.session.mobileNo || '';
  if (field === 'client_id') return state.session.clientCode || '';
  return '';
}

/**
 * Render the widget for a report_request frame and resolve with the structured
 * params on submit. The widget is the ONLY source of report parameter values.
 */
function showReportWidget(reportType, fields) {
  return new Promise((resolve) => {
    removeEmptyState();
    const meta = REPORT_TITLES[reportType] || { title: reportType, blurb: '' };
    const card = document.createElement('div');
    card.className = 'flex justify-start msg-in';

    const fieldRows = fields
      .map((f) => {
        const fm = FIELD_META[f] || { label: f, type: 'text', placeholder: '' };
        const prefill = escapeHtml(prefillFor(f));
        return `
          <label class="block">
            <span class="block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 mb-1">${fm.label}</span>
            <input data-field="${f}" type="${fm.type}" value="${fm.type === 'date' ? '' : prefill}"
                   placeholder="${fm.placeholder}" required
                   class="input-field !py-2.5" />
          </label>`;
      })
      .join('');

    card.innerHTML = `
      <div class="report-widget max-w-[92%] sm:max-w-[26rem] w-full p-5">
        <div class="flex items-center gap-2.5 mb-1">
          <div class="brand-tile w-8 h-8 rounded-xl flex items-center justify-center shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="white" class="w-4 h-4">
              <path fill-rule="evenodd" d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z" clip-rule="evenodd"/>
            </svg>
          </div>
          <div>
            <p class="font-display font-semibold text-[15px] leading-tight text-slate-100">${meta.title}</p>
            <p class="text-[12px] text-slate-400">${meta.blurb}</p>
          </div>
        </div>
        <p class="text-[12px] text-cyan-200/90 bg-cyan-400/10 border border-cyan-300/15 rounded-lg px-2.5 py-1.5 my-3.5">
          🔒 These details go straight to FinX — never through the AI.
        </p>
        <form class="space-y-3">${fieldRows}
          <div class="flex gap-2 pt-0.5">
            <button type="button" data-cancel
                    class="shrink-0 min-h-[44px] px-4 rounded-xl text-[13px] font-medium text-slate-400
                           border border-white/10 bg-white/5 hover:text-white hover:bg-white/10
                           transition-colors disabled:opacity-50">
              Never mind
            </button>
            <button type="submit"
                    class="btn-press btn-shine flex-1 min-h-[44px] rounded-xl font-display font-semibold text-white text-sm
                           bg-gradient-to-r from-brand-600 to-cyan-500 shadow-glow
                           transition-shadow duration-300 hover:shadow-lift
                           disabled:opacity-60 disabled:cursor-wait">
              Get my report →
            </button>
          </div>
        </form>
      </div>`;

    messagesEl.appendChild(card);
    scrollToEnd(true);

    const form = card.querySelector('form');
    const lockWidget = () => {
      for (const el of form.querySelectorAll('input, button')) el.disabled = true;
      card.querySelector('.report-widget').classList.add('done');
    };

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const params = {};
      for (const input of form.querySelectorAll('input[data-field]')) {
        const field = input.dataset.field;
        const value = input.value.trim();
        params[field] = input.type === 'date' ? toDdMmYyyy(value) : value;
      }
      lockWidget();
      form.querySelector('button[type="submit"]').textContent = 'Pulling your report…';
      resolve(params);
    });

    // Skip path: resolves null — the caller never touches /report.
    form.querySelector('[data-cancel]').addEventListener('click', () => {
      lockWidget();
      form.querySelector('button[type="submit"]').textContent = 'Report skipped';
      resolve(null);
    });
  });
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
 * Consume one SSE stream into an assistant bubble.
 * Resolves {pause: {toolUseId, reportType, fields} | null, text, errored}.
 */
function consumeStream(path, body, bubble) {
  return new Promise((resolve, reject) => {
    let pause = null;
    let errored = false;
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
          pause = { toolUseId: data.tool_use_id, reportType: data.report_type, fields: data.fields };
          break;
        case 'done':
          break;
        case 'error':
          errored = true;
          bubble.fail(data.message || 'Something went wrong.');
          break;
      }
    }).then(() => resolve({ pause, text: bubble.text, errored }), reject);
  });
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
  try {
    const outcome = await consumeStream(
      '/chat',
      {
        session_id: state.session.id,
        messages: state.messages,
        prior_cost_inr: state.cumulativeCost,
      },
      bubble,
    );

    if (outcome.pause) {
      await handleReportPause(outcome, bubble);
    } else {
      bubble.finish();
      if (!outcome.errored) {
        state.messages.push({ role: 'assistant', content: outcome.text });
      } else {
        state.messages.pop(); // failed turn: drop the user msg so history stays clean
        bubble.attachRetry(text);
      }
    }
  } catch (err) {
    bubble.fail(err.message || 'Network error — is the backend running?');
    state.messages.pop();
    bubble.attachRetry(text);
  } finally {
    setBusy(false);
  }
}

/**
 * Bridge a report_request pause: synthesize the paused assistant tool_use
 * message (the loop requires messages to END with it), collect params via the
 * widget, POST /report, and stream the summary into a fresh bubble.
 *
 * Durable history keeps only plain text turns — the tool_use/tool_result
 * exchange lives solely in the /report call's message snapshot.
 */
async function handleReportPause(outcome, pauseBubble) {
  const { toolUseId, reportType, fields } = outcome.pause;
  pauseBubble.finish();

  const assistantContent = [];
  if (outcome.text) assistantContent.push({ type: 'text', text: outcome.text });
  assistantContent.push({
    type: 'tool_use',
    id: toolUseId,
    name: REPORT_TOOL_NAMES[reportType],
    input: {},
  });
  const resumeMessages = [...state.messages, { role: 'assistant', content: assistantContent }];

  const params = await showReportWidget(reportType, fields);

  // User skipped the report: nothing is sent to /report. Keep durable history
  // valid — push the pause text (if any) as a plain assistant turn; otherwise
  // leave history as-is (consecutive user turns are valid for the API).
  if (!params) {
    if (outcome.text) state.messages.push({ role: 'assistant', content: outcome.text });
    return;
  }

  const bubble = addAssistantMessage();
  bubble.setStatus('Fetching your report from FinX…');
  try {
    const resumed = await consumeStream(
      '/report',
      {
        session_id: state.session.id,
        report_type: reportType,
        params,
        tool_use_id: toolUseId,
        messages: resumeMessages,
        prior_cost_inr: state.cumulativeCost,
      },
      bubble,
    );
    bubble.finish();
    if (!resumed.errored) {
      const full = [outcome.text, resumed.text].filter(Boolean).join('\n\n');
      state.messages.push({ role: 'assistant', content: full || '(report delivered)' });
    } else {
      const dropped = state.messages.pop();
      bubble.attachRetry(typeof dropped.content === 'string' ? dropped.content : '');
    }
  } catch (err) {
    bubble.fail(err.message || 'Report request failed.');
    const dropped = state.messages.pop();
    bubble.attachRetry(typeof dropped.content === 'string' ? dropped.content : '');
  }
}

// ---------------------------------------------------------------------------
// Login / logout
// ---------------------------------------------------------------------------

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('login-btn');
  const errEl = $('login-error');
  errEl.classList.add('hidden');

  // spec: trim ALL inputs before POST /session
  const mobileNo = $('login-phone').value.trim();
  const userId = $('login-userid').value.trim();
  const sessionToken = $('login-token').value.trim();
  const clientCode = $('login-clientcode').value.trim();

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
        ...(clientCode ? { clientCode } : {}),
      }),
    });
    if (!res.ok) throw new Error(`login failed (${res.status})`);
    const data = await res.json();

    state.session = { id: data.session_id, userId, mobileNo, clientCode };
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
