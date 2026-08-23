
const $ = (id) => document.getElementById(id);
//small notification on screen for 4 seconds 
let toastTimer;
function toast(message, kind = '') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}

function percent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function scoreClass(score) {
  if (score >= 0.7) return 'score-good';
  return score >= 0.45 ? 'score-mid' : 'score-bad';
}
//display date in a human readable format
function shortDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}
//button that starts an operation that takes some time.
async function withBusy(button, label, action) {
  const original = button.textContent;
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span>${label}`;
  try {
    await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}
//apoorvab
//take text from the backend/LLM and convert it into HTML so it can be displayed nicely on webpage
function renderMarkdown(text) {
  const safe = escapeHtml(text);
  const lines = safe.split('\n');
  const html = [];
  let inList = false;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      //end of list
      if (inList) { html.push('</ul>'); inList = false; }
      continue;
    }
    const bolded = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (line.startsWith('- ') || line.startsWith('* ')) {
      //start of list
      if (!inList) { html.push('<ul>'); inList = true; }
      html.push(`<li>${bolded.slice(2)}</li>`);//remove that -* in start
    } else {
      if (inList) { html.push('</ul>'); inList = false; }
      html.push(`<p>${bolded}</p>`);
    }
  }
  if (inList) html.push('</ul>');
  return html.join('');
}
//adding the hidden CSS class, so the login/signup screen disappears.
function showApp(email) {
  $('auth-view').classList.add('hidden');
  $('app-view').classList.remove('hidden');
  $('user-email').textContent = email || '';
  loadDocuments();
}

function showAuth() {
  $('app-view').classList.add('hidden');
  $('auth-view').classList.remove('hidden');
}
//user clicks tabs, logs in, signs up, logs out, uploads a resume, or uploads a job description.
function switchTab(name) {
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  ['upload', 'match', 'search', 'history'].forEach((tab) => {
    $(`tab-${tab}`).classList.toggle('hidden', tab !== name);
  });
  if (name === 'match') loadDocuments();
  if (name === 'search') {
    loadDocuments();
    loadVectorStats();
  }
  if (name === 'history') loadHistory();
}

document.querySelectorAll('[data-auth-tab]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.authTab;
    document.querySelectorAll('[data-auth-tab]').forEach((b) => {
      b.classList.toggle('active', b === btn);
    });
    $('login-form').classList.toggle('hidden', target !== 'login');
    $('signup-form').classList.toggle('hidden', target !== 'signup');
  });
});

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = $('login-email').value.trim();
  const { ok, data } = await API.login(email, $('login-password').value);
  if (!ok) return toast(data, 'error');
  API.setToken(data.access_token);
  showApp(email);
});

$('signup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = $('signup-email').value.trim();
  const { ok, data } = await API.signup(email, $('signup-password').value);
  if (!ok) return toast(data, 'error');
  API.setToken(data.access_token);
  showApp(email);
});

$('logout-btn').addEventListener('click', () => {
  API.setToken(null);
  showAuth();
});

document.querySelectorAll('[data-tab]').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

$('upload-resume-btn').addEventListener('click', (event) => {
  const file = $('resume-file').files[0];
  if (!file) return toast('Choose a resume file first.', 'error');

  withBusy(event.target, 'Parsing...', async () => {
    const { ok, data } = await API.uploadResume(file);
    if (!ok) return toast(data, 'error');
    toast('Resume saved.', 'success');
    $('resume-file').value = '';
    loadDocuments();
  });
});

$('upload-jd-btn').addEventListener('click', (event) => {
  const file = $('jd-file').files[0];
  const text = $('jd-text').value.trim();
  if (!file && !text) return toast('Paste some text or choose a file.', 'error');

  withBusy(event.target, 'Saving...', async () => {
    const { ok, data } = file
      ? await API.uploadJdFile(file)
      : await API.uploadJdText(text);
    if (!ok) return toast(data, 'error');
    toast('Job description saved.', 'success');
    $('jd-text').value = '';
    $('jd-file').value = '';
    loadDocuments();
  });
});
//puts uploaded resumes and job descriptions into the dropdowns.

function fillSelect(select, items) {
  if (!items.length) {
    select.innerHTML = '<option value="">Nothing uploaded yet</option>';
    return;
  }
  select.innerHTML = items
    .map((doc) => {
      const label = `${shortDate(doc.created_at)} - ${doc.preview.slice(0, 60)}...`;
      return `<option value="${escapeHtml(doc.id)}">${escapeHtml(label)}</option>`;
    })
    .join('');
}

async function loadDocuments() {
  const [resumes, jds] = await Promise.all([API.listResumes(), API.listJds()]);
  if (resumes.ok) fillSelect($('resume-select'), resumes.data);
  if (jds.ok) {
    fillSelect($('jd-select'), jds.data);
    fillSelect($('search-jd-select'), jds.data);
  }
}

$('run-match-btn').addEventListener('click', (event) => {
  const resumeId = $('resume-select').value;
  const jdId = $('jd-select').value;
  if (!resumeId || !jdId) return toast('Upload a resume and a JD first.', 'error');

  withBusy(event.target, 'Scoring...', async () => {
    const { ok, data } = await API.createMatch(resumeId, jdId);
    if (!ok) return toast(data, 'error');
    renderMatch(data);
  });
});

function renderMatch(match) {
  const features = match.features || {};
  const panel = $('match-result');

  panel.innerHTML = `
    <div class="card">
      <div class="score-big ${scoreClass(match.final_score)}">
        ${percent(match.final_score)}
      </div>
      <p class="muted">Overall match score</p>

      <div class="metrics">
        <div class="metric">
          <div class="label">Embedding similarity</div>
          <div class="value">${percent(match.cosine_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Cross-encoder</div>
          <div class="value">${percent(match.cross_encoder_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Keyword overlap</div>
          <div class="value">${percent(features.keyword_overlap)}</div>
        </div>
        <div class="metric">
          <div class="label">Years match</div>
          <div class="value">${percent(features.years_match)}</div>
        </div>
        <div class="metric">
          <div class="label">Education match</div>
          <div class="value">${percent(features.education_match)}</div>
        </div>
      </div>

      <details>
        <summary>Raw feature values</summary>
        <pre>${escapeHtml(JSON.stringify(features, null, 2))}</pre>
      </details>

      <div class="explanation">${renderMarkdown(match.explanation_text)}</div>

      <hr class="divider">

      <h3>Was this score right?</h3>
      <div class="btn-row">
        <button class="btn" id="fb-up">Looks right</button>
        <button class="btn" id="fb-down">Looks wrong</button>
      </div>

      <details>
        <summary>Give a corrected score instead</summary>
        <label for="fb-slider">What should it have been?</label>
        <div class="slider-row">
          <input id="fb-slider" type="range" min="0" max="100" step="5" value="50">
          <span class="slider-value" id="fb-slider-value">50%</span>
        </div>
        <label for="fb-comment">Anything to add? (optional)</label>
        <input id="fb-comment" type="text">
        <button class="btn primary" id="fb-submit">Submit correction</button>
      </details>
    </div>
  `;
  panel.classList.remove('hidden');
  wireFeedback(match.id);
}

function wireFeedback(matchId) {
  const slider = $('fb-slider');
  slider.addEventListener('input', () => {
    $('fb-slider-value').textContent = `${slider.value}%`;
  });

  const send = async (rating, corrected, comment) => {
    const { ok, data } = await API.submitFeedback(matchId, rating, corrected, comment);
    toast(
      ok ? 'Thanks - this feeds the next retraining run.' : data,
      ok ? 'success' : 'error',
    );
  };

  $('fb-up').addEventListener('click', () => send(1, null, ''));
  $('fb-down').addEventListener('click', () => send(-1, null, ''));

  // A correction implies the original was wrong, hence rating -1.
  $('fb-submit').addEventListener('click', () =>
    send(-1, Number(slider.value) / 100, $('fb-comment').value),
  );
}

// --- Vector search ------------------------------------------------------
// Ranks the whole resume collection against one JD (or free text) using
// Chroma, with the metadata filters applied before the ranking.

async function loadVectorStats() {
  const { ok, data } = await API.vectorStats();
  $('vector-stats').textContent = ok
    ? `${data.resume_vectors} resume / ${data.jd_vectors} JD vectors indexed`
    : 'Vector index unavailable';
}

// Blank inputs mean "no filter", so they're left out of the request entirely
// rather than sent as null -- the server applies only the keys it receives.
function collectFilters() {
  const filters = {};

  const years = $('filter-years').value.trim();
  if (years !== '') filters.min_years = Number(years);

  const degree = $('filter-degree').value;
  if (degree) filters.min_degree_rank = Number(degree);

  const source = $('filter-source').value;
  if (source) filters.source = source;

  const contains = $('filter-contains').value.trim();
  if (contains) filters.must_contain = contains;

  return filters;
}

$('run-search-btn').addEventListener('click', (event) => {
  const text = $('search-text').value.trim();
  const jdId = $('search-jd-select').value;

  // Typed text wins over the dropdown, since typing it is the more explicit act.
  if (!text && !jdId) {
    return toast('Upload a job description, or type what to search for.', 'error');
  }

  const body = {
    k: Number($('filter-k').value) || 5,
    filters: collectFilters(),
  };
  if (text) body.query_text = text;
  else body.query_id = jdId;

  withBusy(event.target, 'Searching...', async () => {
    const { ok, data } = await API.searchResumes(body);
    if (!ok) return toast(data, 'error');
    renderSearchResults(data);
    loadVectorStats();
  });
});

function renderHit(hit, index) {
  const chips = [];
  if (hit.years_experience != null) {
    chips.push(`${hit.years_experience} yrs`);
  }
  const degrees = { 1: 'Bachelors', 2: 'Masters', 3: 'Doctorate' };
  if (degrees[hit.degree_rank]) chips.push(degrees[hit.degree_rank]);
  if (hit.filename) chips.push(hit.filename);
  else if (hit.source === 'text') chips.push('pasted text');
  if (hit.created_at) chips.push(shortDate(hit.created_at));

  const width = Math.round((hit.similarity || 0) * 100);

  return `
    <div class="hit">
      <div class="hit-rank">${index + 1}</div>
      <div class="hit-body">
        <div class="hit-head">
          <strong class="small">Resume ${escapeHtml(hit.id.slice(-6))}</strong>
          <span class="hit-score ${scoreClass(hit.similarity)}">
            ${percent(hit.similarity)}
          </span>
        </div>
        <div class="hit-bar"><span style="width: ${width}%"></span></div>
        <p class="hit-preview">${escapeHtml(hit.preview)}...</p>
        <div class="hit-meta">
          ${chips.map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join('')}
        </div>
      </div>
    </div>`;
}

function renderSearchResults(result) {
  const panel = $('search-result');
  const filters = (result.filters_applied || [])
    .map((f) => `<span class="chip">${escapeHtml(f)}</span>`)
    .join('');

  const body = result.hits.length
    ? result.hits.map(renderHit).join('')
    : `<p class="muted">Nothing matched. The filters may be too narrow -- they
       are applied before ranking, so a strict filter can empty the results
       even when similar documents exist.</p>`;

  panel.innerHTML = `
    <div class="card">
      <h2>${result.count} result${result.count === 1 ? '' : 's'}</h2>
      <p class="muted small">
        Ranked by cosine similarity between the query embedding and each stored
        resume embedding.
      </p>
      ${body}
      <div class="applied-filters">
        <div class="label muted small">Filters Chroma applied</div>
        <div class="hit-meta">${filters}</div>
      </div>
    </div>`;
  panel.classList.remove('hidden');
}

async function loadHistory() {
  const list = $('history-list');
  const { ok, data } = await API.listMatches();

  if (!ok) {
    list.innerHTML = `<p class="muted">${escapeHtml(data)}</p>`;
    return;
  }
  if (!data.length) {
    list.innerHTML = '<p class="muted">No matches yet.</p>';
    return;
  }

  list.innerHTML = data
    .map(
      (match) => `
      <div class="history-item">
        <details>
          <summary>
            <span class="${scoreClass(match.final_score)}">
              ${percent(match.final_score)}
            </span>
            &nbsp;&mdash;&nbsp;
            <span class="muted small">${shortDate(match.created_at)}</span>
          </summary>
          <div class="explanation">${renderMarkdown(match.explanation_text)}</div>
        </details>
      </div>`,
    )
    .join('');
}

(async function start() {
  if (!API.isLoggedIn()) return showAuth();
  // Validate the stored token before trusting it -- it may have expired
  // while the tab was closed.
  const { ok, data } = await API.me();
  if (ok) showApp(data.email);
  else showAuth();
})();
