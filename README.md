# Browser Agent

Two implementations of the same agent, plus the app they are verified against.

| Path | What it is |
|---|---|
| `browser_agent.py` | Playwright, out-of-process. **Primary.** |
| `agent-extension/` | Chrome MV3, in-page. Secondary. |
| `testapp/` | A three-step form to drive; also the replay regression fixture. |
| `tests/` | 32 tests. No API key required. |

## Architecture invariants

These are the design, not incidental choices. Both implementations hold them.

1. **Perception is DOM refs, not pixels.** Each snapshot stamps the visible
   interactive elements with `data-agent-ref="e7"` and returns a structured
   record per element. No coordinates, no screenshots in the hot path.
2. **The action space is closed.** Eleven verbs, declared once and handed to
   the model as a `strict` tool schema, so an invalid `kind` is rejected by the
   API before it reaches the page. No verb carries a selector or a code string.
3. **Every action is verified.** The loop re-perceives after acting, compares
   fingerprints, and aborts after three consecutive no-ops.
4. **The history window stays small.** The prompt carries the last six steps,
   never the full transcript.
5. **In the extension, the loop lives in the service worker.** Navigation
   destroys the content script, so nothing that must survive a page transition
   is kept in the page.

## Quick start

Clone it and pick the branch:

```bash
git clone https://github.com/spinfern-o/website-completer.git
cd website-completer
git checkout claude/new-session-rb8pxn
```

Check your Python first — both `anthropic` and `playwright` require **3.10 or
newer**, and the `python3` that ships with macOS is 3.9:

```bash
python3 --version
```

If that prints 3.9.x, install a newer one (`brew install python@3.12`, or from
python.org) and use it for the next step in place of `python3`.

Then install into a virtualenv. Recent macOS and Linux Pythons refuse to
install into the system interpreter, so the venv is not optional there.
Playwright ships its own Chromium and has to fetch it once:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Start the test app. It runs in the foreground, so give it a terminal of its
own and leave it there:

```bash
cd testapp
npm install
npm run dev
```

Before the first real run, check the API path for the cost of a single call —
no browser, no dev server:

```bash
python3 tools/check_model.py
```

It prints the action the model returned, or a `FAILED` line naming the
exception. Note the test suite deliberately never imports `anthropic`
(replay needs neither the SDK nor a key), so this script is the first thing
that proves your key and the request shape both work.

In a second terminal, from the repo root, run the agent against it:

```bash
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-your-real-key
python3 browser_agent.py --goal "Complete the enrollment form as Ada Lovelace (ada@example.com), Standard plan, Express delivery, then report the reference number."
```

Or do all of it with one command — it starts the test app, runs the agent,
replays the trace, and replays it again against a shifted page:

```bash
./demo.sh
./demo.sh --replay
```

`--replay` skips the paid run and uses an existing trace, so it costs nothing.

A successful run writes `trace.json`. Replay it with no model call at all —
the second command replays against the shifted page:

```bash
python3 browser_agent.py --replay
python3 browser_agent.py --replay --url 'http://localhost:3000/?nav=1'
```

If a package suddenly goes missing from an apparently active venv, check
`which python3` — anything that re-runs `~/.zshrc` can push a system Python
ahead of the venv on PATH, and the `(.venv)` prompt keeps showing regardless.
Calling `.venv/bin/python` directly sidesteps it entirely.

### Choosing a model

`--model` changes the request shape, not just the name. Current models
(Opus 5/4.8/4.7/4.6, Sonnet 5/4.6, Fable 5) take adaptive thinking and
`--effort`; older ones (Haiku 4.5, Sonnet 4.5) reject both, and the agent omits
them rather than sending a request the API refuses. `--effort` on a model that
does not support it prints a note instead of being silently dropped.

For mechanical work — clicking through a form or a quiz — a smaller model is
usually the better buy, since each step is a simple decision rather than one
needing deep reasoning:

```bash
python3 browser_agent.py --model claude-haiku-4-5 --max-steps 40 --url '...'
```

Thinking tokens bill as output, so `--effort low` is a larger lever on cost
than the element cap, and the model is larger still.

Useful flags: `--headed`, `--max-steps`, `--model`, `--effort`, `--no-record`, and
`--pw-trace out.zip` for a Playwright trace (`playwright show-trace out.zip` is
the fastest way to see where a run went wrong).

## Running against a site behind a login

Every run starts a fresh, anonymous browser context, so a site with a sign-in
drops the agent on a login page. Log in once by hand and save what the browser
is holding:

```bash
python3 tools/login.py --url https://example.com/login --session session.json
```

A real browser window opens. Sign in there yourself — password, 2FA, whatever
the site asks — then press Enter back in the terminal. The cookies and
per-origin localStorage are written to `session.json`, and runs that pass
`--session` start already logged in:

```bash
python3 browser_agent.py --session session.json --url https://example.com/start --goal "..."
```

The agent never sees or handles your password; it only inherits a session the
browser already established. Each run writes the session back, so a rotated
cookie survives to the next one.

**Treat `session.json` as a credential.** Anyone holding it is logged in as you
until it expires. It is written `0600` and gitignored (`session.json`,
`*.session.json`), and there is a test asserting it stays that way. Delete it
when you are done, and expect to redo the login when the site expires it.

If the saved session comes back empty, `tools/login.py` says so: the site keys
its session to something `storage_state` does not capture, and this approach
will not work for it.

### Testing the session path locally

The test app ships a sign-in fixture so the whole login flow can be exercised
without involving any real identity provider. `?sso=1` puts the app behind a
redirect-based sign-in served from a second origin (`testapp/idp/`, on port
3001), which hands a token back the way an SSO handshake does. The resulting
session is split across both origins — a cookie on the app, the provider's own
entry on the provider — which is the shape that actually matters, and the usual
reason a captured session fails is that only one half was kept.

Serve both, then run the real login flow against them:

```bash
python3 -m http.server 3000 --directory testapp/dist &
cd testapp/idp && python3 -m http.server 3001 &

python3 tools/login.py --url 'http://localhost:3000/?sso=1' --session session.json
python3 browser_agent.py --session session.json --url 'http://localhost:3000/?sso=1'
```

Any non-empty username and password are accepted. `tests/test_sso.py` runs the
same round trip headlessly: gated without a session, through the provider and
back, captured, and restored into a fresh context that skips the login entirely.

### Look before you run

Before spending anything on a new target, print the snapshot the model would
see. No API call, no cost:

```bash
python3 tools/inspect_page.py --url 'https://example.com/page'
python3 tools/inspect_page.py --url '...' --session session.json --wait 5
```

It shows the elements and text exactly as the model receives them, then flags
what would break a run: no interactive elements at all, an iframe holding the
real content, controls with no accessible name, or a page large enough to hit
the element or text caps. Most first-run failures are visible here.

### Frames

Perception reaches into child frames, because that is where real applications
put their content — embedded players, editors, and most third-party widgets are
iframes, and a top-document-only snapshot sees an empty page.

Refs are namespaced by frame: `e3` is in the main document, `f1e3` is inside
the first child frame, and the snapshot labels them `frame=1`. The prefix is
how an action reaches the right frame; a locator built against the wrong one
finds nothing. Frame text is folded into the snapshot under an `[f1]` marker so
the model reads the content along with the controls.

The element budget is shared across frames rather than applied per frame, so a
page of many small frames cannot crowd out the main document.

### What else a real site will need

Beyond login, the gaps between the test app and a production one:

- **Size caps** — 120 elements per snapshot across all frames, 4000 characters
  of page text. A dense app exceeds both, and the agent cannot see past the
  cut. `--max-elements` raises the first; it costs input tokens on every step.
- **Step budget** — `MAX_STEPS` defaults to 30, and each step is one API call.
- **Deliberately absent** — no CAPTCHA solving, bot-detection evasion, mouse
  jitter, or spoofed focus/visibility/media events. A page gating on "was this
  actually watched" has no verb here and will not get one.

## Replay, and why steps record names

Replay is the bottom rung of the determinism ladder: a run that succeeded once
should repeat for free. That only works if a recorded step can find its target
again on a page that has drifted.

Refs are positions within a single snapshot. They are renumbered on every
snapshot, so a trace that stores only a ref is really storing "the seventh
interactive element" — and the moment the page grows a nav link, the seventh
element is something else. So each `Step` persists the target's **accessible
name, tag, and type**, captured at action time, and replay matches on those.
The recorded ref survives only as a tie-breaker between otherwise identical
candidates.

Matching relaxes in order: `(name, tag, type)` → `(name, tag)` → `name`. If the
name resolves to nothing, replay **bails** rather than falling back to the ref;
a vanished name means the page genuinely changed, and clicking whatever now sits
at that position is the bug, not the recovery. `main()` then re-navigates to
`start_url` before handing over to the model, so a partial replay never leaves
the model staring at the middle of a flow it did not start.

`testapp`'s `?nav=1` inserts an `<a>` above the form, which shifts every ref
after it. That is the regression fixture, and `tests/test_replay.py` asserts
both halves: name-matched replay survives it, and ref-only replay demonstrably
does not.

## The test app

Vite + React on `localhost:3000`.

- **Step 1** — three text inputs. All are React-controlled, so a direct
  `el.value = x` is swallowed and the `setNativeValue` path in the extension is
  genuinely exercised.
- **Step 2** — a select, a checkbox, and a radio group.
- **Step 3** — review, then submit to a confirmation page with a generated
  reference number.
- `?slow=1` delays each step's render by 2s.
- `?nav=1` inserts a link above the form (the replay fixture).

## The extension

Load `agent-extension/` unpacked at `chrome://extensions`. The popup takes a
goal and an API key, and shows the step log live; the run continues in the
worker if you close it.

`host_permissions` is scoped to `localhost:3000` and the API origin. Widen it to
the specific origins you are automating — not `<all_urls>`, which is both
unnecessary and what gets an extension rejected from review.

**On the API key:** the popup stores it in `chrome.storage.local` and the worker
calls the API directly. That is reasonable for a local dev tool against apps you
control, and not something to ship to other people — anything with access to the
extension's storage has the key. For anything beyond local use, point
`API_URL` at a relay you own and keep the key server-side.

## Running the tests

With the virtualenv active, and `npm install` already run once in `testapp`:

```bash
python3 -m pytest tests/ -q
```

The suite builds `testapp` if needed and serves it on an ephemeral port, so
there is no dev server to start and no port to collide on. The model is stood in
for by a script that resolves refs by reading the rendered prompt — which means
the tests also fail if the prompt stops being legible to a model. No API key is
needed.

Syntax checks, as in the spec:

```bash
python3 -m py_compile browser_agent.py
node --check agent-extension/*.js
```

## Scope

Targets are apps you control or have permission to automate: the `testapp`, your
own staging environments, internal tools. `navigate` is origin-guarded to the
start URL's origin, and the model cannot express a navigation outside it.

Deliberately absent, and not to be added: CAPTCHA solving, bot-detection
evasion, synthetic mouse jitter, and spoofed focus/visibility/media events. None
of it serves the automation, all of it is brittle, and it turns a maintainable
tool into one that breaks on every vendor update.
# three-statement-dcf
