/* Node check for the two pure render helpers in app.js.
   They're extracted by regex so this stays in sync with the real source
   rather than testing a copy.

   Run: node test_render.js  (from the frontend/ directory) */

const fs = require('fs');

const source = fs.readFileSync(`${__dirname}/app.js`, 'utf8');

function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`${name} not found in app.js`);
  // Walk braces to find the end of the function body.
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unbalanced braces in ${name}`);
}

// escapeHtml uses the DOM; stub just enough of it.
global.document = {
  createElement: () => ({
    set textContent(value) {
      this._html = String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    },
    get innerHTML() {
      return this._html;
    },
  }),
};

eval(extract('escapeHtml'));
eval(extract('renderMarkdown'));
eval(extract('percent'));
eval(extract('scoreClass'));

let failures = 0;
function check(label, actual, expected) {
  const ok = actual === expected;
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) console.log(`        got:  ${actual}\n        want: ${expected}`);
}

// A real explanation, copied verbatim from an API response.
const REAL_EXPLANATION = [
  '**Overall:** this resume scores 82% against the job description.',
  '',
  '**Terms in the job description not found in the resume**',
  '- bachelors',
  '- engineer',
  '- degree',
  '',
  '_(Generated without an LLM. Set GROQ_API_KEY for a written explanation.)_',
].join('\n');

const rendered = renderMarkdown(REAL_EXPLANATION);
console.log('--- rendered real explanation ---');
console.log(rendered);
console.log();

check('bold becomes <strong>', rendered.includes('<strong>Overall:</strong>'), true);
check('bullets become <li>', rendered.includes('<li>bachelors</li>'), true);
check('list is wrapped in <ul>', rendered.includes('<ul>'), true);
check('lists are closed', (rendered.match(/<ul>/g) || []).length === (rendered.match(/<\/ul>/g) || []).length, true);

// --- XSS: LLM output and file previews are untrusted ---
const evil = '**Hi** <img src=x onerror=alert(1)>\n- <script>alert(2)</script>\n- a & b';
const out = renderMarkdown(evil);
console.log('--- rendered hostile input ---');
console.log(out);
console.log();

check('script tag is escaped', out.includes('&lt;script&gt;'), true);
check('no live script tag', out.includes('<script>'), false);
check('no live onerror handler', /<img[^>]*onerror/.test(out), false);
check('ampersand escaped', out.includes('a &amp; b'), true);
check('intended bold still works', out.includes('<strong>Hi</strong>'), true);

// --- number formatting ---
check('percent(0.661)', percent(0.661), '66%');
check('percent(0)', percent(0), '0%');
check('percent(undefined)', percent(undefined), '0%');
check('percent(1)', percent(1), '100%');

check('scoreClass(0.82)', scoreClass(0.82), 'score-good');
check('scoreClass(0.5)', scoreClass(0.5), 'score-mid');
check('scoreClass(0.2)', scoreClass(0.2), 'score-bad');

console.log(`\n${failures === 0 ? 'All checks passed.' : failures + ' FAILED'}`);
process.exit(failures === 0 ? 0 : 1);
