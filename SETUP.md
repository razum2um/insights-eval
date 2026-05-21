# Setup, running, and viewing results

## Prerequisites

- **`uv`** — this is a uv project; all commands are `uv run …`.
- **A local PostgreSQL** reachable on `localhost:5432`, with create-database
  rights for your user (peer/trust auth is fine).
- **The `insights` repo** checked out locally with its own venv synced
  (`uv sync` inside it). The eval launches the *real* insights MCP server
  out of that checkout — point `INSIGHTS_REPO` at it. From human to human:
  sorry, it's a private repo.
- **A model API key** (e.g. `ANTHROPIC_API_KEY`) to run the eval against a
  real model. The unit tests need no key.

## Quick start

```bash
make setup          # uv sync this project
make seed           # create + seed the `insights_eval` Postgres database
make test           # 24 unit tests — no API key, no model

# run the eval against a real model
export ANTHROPIC_API_KEY=...
make eval                                  # all 15 samples
make eval MODEL=anthropic/claude-opus-4-7  # pick the model
make eval-quick                            # 3-sample smoke test
make view                                  # open the Inspect log viewer
```

For a self-hosted (vLLM) target instead of a hosted API, see
[`vllm/README.md`](vllm/README.md).

## Viewing results

`make view` (= `uv run inspect view`) starts the Inspect log viewer at
**http://localhost:7575** — it auto-discovers `./logs`, and lets you drill
into each sample's transcript, tool calls, and per-scorer verdicts.

### Serving the viewer to others

`inspect view` is a live server, not a static page. To expose it:

```bash
uv run inspect view --host 0.0.0.0 --port 7575
```

It has **no authentication** and eval transcripts can be sensitive, so do
not put `0.0.0.0` on a public interface. Prefer either an SSH tunnel —

```bash
ssh -L 7575:localhost:7575 user@host    # then open localhost:7575 locally
```

— or a reverse proxy (nginx/Caddy/Cloudflare Access) that adds auth.

### Static export — GitHub Pages, Netlify, S3, …

`inspect view` itself can't run on GitHub Pages (Pages serves static files
only). But Inspect ships a **static bundler** for exactly this:

```bash
uv run inspect view bundle --log-dir logs --output-dir site --overwrite
```

That writes a self-contained static site (`site/index.html` + `assets/` +
an embedded copy of `logs/`) — no server needed. Deploy it anywhere static:

- **GitHub Pages** — push `site/` to a `gh-pages` branch (or wire the
  workflow below), then enable Pages for that branch.
- **Netlify / Cloudflare Pages / S3** — point the host at `site/`.

The bundle **embeds the full eval transcripts**. On a public Pages site
those become public — fine for this eval's synthetic data, but review
before publishing anything real.

A ready GitHub Actions workflow lives at
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) — it rebuilds
the bundle and deploys to Pages on every push to `main` (and on manual
dispatch). One-time setup: repo **Settings → Pages → Source = "GitHub
Actions"**.

By default `.gitignore` excludes `logs/*.eval`, so there is nothing to
publish until you either commit the specific `.eval` file you want public
(`git add -f logs/<file>.eval`) or extend the workflow's build job to run
the eval itself.
