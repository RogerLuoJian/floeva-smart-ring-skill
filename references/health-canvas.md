# Floeva Health Canvas

Read this reference before creating or operating the immersive health report.

## When to use it

Create a Health Canvas when the user asks for a health overview, dashboard,
chart, graph, visual report, or a prettier presentation. If a local browser is
available, prefer the Canvas for a complete overview unless the user asks for
text only. Continue to include a short text finding in the conversation so the
answer remains useful if the browser cannot be opened.

The Canvas is not a generic analytics dashboard. It is an editorial health
portrait: one large rhythm landscape, a compact insight rail, clear coverage,
and warm language. It must stay non-diagnostic.

## Prepare and serve

Locate `scripts/floeva-report.py` beside `SKILL.md`, using the same installed
directory resolution as the authorization helper.

1. Confirm authorization with `floeva-auth.sh status`.
2. Prepare a report. The helper fetches the official overview itself so the
   credential never has to appear in an Agent command:

   ```bash
   python3 <skill-dir>/scripts/floeva-report.py prepare
   ```

3. Parse the single JSON line. It contains only a local `url`, opaque
   `session`, expiry, and non-secret summary. Do not alter or guess the URL.
4. Before starting a server, request `http://127.0.0.1:5176/healthz`. Reuse the
   port only when the response is HTTP 200 and the exact `app` value is
   `floeva-health-canvas`. A different service on that port is a conflict.
5. If needed, start the long-running server and keep its process handle:

   ```bash
   python3 <skill-dir>/scripts/floeva-report.py serve --port 5176
   ```

   Wait for the line beginning `READY` before opening the report URL.
6. Open the returned local URL. Confirm that the page title is
   `Floeva Health Canvas`, the main heading is `身体节律`, and the latest-date
   summary agrees with the safe summary returned by `prepare`.
7. Tell the user the report is local and expires in one hour. When the user is
   done, remove that exact session:

   ```bash
   python3 <skill-dir>/scripts/floeva-report.py cleanup <session>
   ```

Stop only the server process started by the current task. Do not kill an
unrelated process that happens to use the same port.

## Data and visual contract

- The main landscape uses recorded activity as its primary contour, with heart
  and sleep signals layered only when those series are available.
- The insight rail shows the latest sleep duration, resting heart rate, HRV,
  steps, baseline maturity, seven-day activity, heart range, and sleep stages.
- Missing values display as `未记录` or `—`; never convert missing data to zero.
- A zero recorded by the service remains a real zero.
- The latest date and the number of recorded days must remain visible.
- Partial same-day activity is labelled as still unfolding; do not compare it
  as if it were a completed day.
- Personal-baseline language appears only when the response explicitly says the
  baseline is personalized.
- Flow is never inferred from the overview. If Flow is requested, query the
  official Flow tool and explain it separately until the Canvas runtime has an
  explicit Flow data contract.

## Privacy and failure behavior

- The browser receives staged health data, never an access token, API key,
  password, device code, config file, or remote API URL.
- Reports live only under a random directory in `~/.floeva/reports`, with
  directory mode `0700`, report mode `0600`, and a one-hour expiry.
- The server binds only to `127.0.0.1`, disables caching and referrers, rejects
  framing, and serves only fixed local assets plus the requested session.
- Do not upload the generated report, screenshot, or health JSON unless the
  user explicitly asks and approves the destination.
- If preparation, serving, or browser opening fails, provide the compact
  Markdown presentation from `data-presentation.md`. Never weaken the local
  security controls to make the visual report work.

## Visual identity

The Canvas is an original Floeva presentation. It uses Floeva's light
lavender-to-warm-peach atmosphere, purple accent, frosted white surfaces,
generous typography, and soft motion. Preserve this visual language when
extending it. Do not copy third-party source, artwork, trademark treatments, or
dark-theme styling.
