# Run everything from your phone — setup

No computer needed. GitHub's free cloud runners execute the bot on a schedule,
publish a live dashboard to a web page, and push alerts to your phone. You manage
it all from the **GitHub app** + your **browser** + the **ntfy app**.

```
GitHub Actions (cloud runner)  ──runs every 2h──▶  scripts/build_site.py
        │                                              │
        ├─ writes docs/  ──▶  GitHub Pages  ──▶  your dashboard URL (open on phone)
        └─ BUY/EXIT flips ──▶  ntfy.sh  ──▶  push notification on your phone
```

Everything is **paper / read-only** — no keys, no real orders anywhere.

## One-time setup (all from your phone, ~5 minutes)

### 1. Apps
- Install **GitHub** (App Store / Play Store) and sign in.
- Install **ntfy** (App Store / Play Store).

### 2. Pick your alert channel (ntfy)
- Open ntfy → **Subscribe to topic** → enter a random, hard-to-guess name, e.g.
  `tradebot-dustin-9f3k2z`. Anyone who knows the topic can see your alerts, so
  keep it unguessable. That's it — no account.

### 3. Tell GitHub your topic (secret)
- In a browser: your repo → **Settings → Secrets and variables → Actions →
  New repository secret**.
- Name: `NTFY_TOPIC` · Value: the topic from step 2 → **Add secret**.
- (Skip this and the dashboard still works — you just won't get pushes.)

### 4. Turn on the dashboard (GitHub Pages)
- Repo → **Settings → Pages**.
- **Source: Deploy from a branch** → Branch: `claude/ampl-trading-bot-rebase-3hjbos`
  → folder **`/docs`** → **Save**.
- After a minute your site URL appears, like
  `https://dustin-hoover.github.io/didactic-waddle/`. Open it on your phone and
  **Add to Home Screen** — it now behaves like an app.

> ⚠️ **Free-plan gotcha:** GitHub Pages only publishes from **public** repos on
> the free plan, and public repos also get **unlimited** Actions minutes (private
> repos get 2,000/month, and every-2-hours ≈ 720/month — tight but fits). There
> are **no secrets in the code** (trading is paper; your ntfy topic lives in the
> encrypted secret, not the code), so making the repo public is safe here. If you
> keep it private on a free plan, the **alerts still work** — only the hosted
> dashboard needs public (or a paid plan).

### 5. Start it
- Repo → **Actions** tab → if prompted, **enable workflows** → open **tradebot**
  → **Run workflow** to fire it once now. After that it runs itself every 2 hours.

## Using it day to day, from your phone
- **Dashboard:** your Pages URL — market regime, the featured backtest, and the
  live screener, refreshed every run.
- **Alerts:** ntfy pings you `BUY BTC` / `EXIT ETH` when a trend flips. You place
  the trade yourself in your own wallet (you keep custody).
- **Control panel:** the GitHub app → Actions shows every run and its logs; hit
  **Run workflow** any time you want a fresh check.
- **Change settings:** edit `.github/workflows/tradebot.yml` right in the GitHub
  app — the `cron` line for frequency, `TB_INTERVAL`/`TB_STYLE` for timeframe.

## Honest limits
- Scheduled runs are **best-effort** — GitHub can delay them a few minutes under
  load. Fine for 4h/daily swing signals; not for fast scalping.
- The dashboard is a **snapshot** refreshed each run, not a live streaming chart.
- This tells you **when** to act and protects the plan in backtests. It does not
  guarantee profit, and it will trail buy-and-hold in a straight bull market.
