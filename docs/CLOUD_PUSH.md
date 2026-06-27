# Automatic updates — cloud push (GitHub Actions)

This runs the snapshot `push` on a schedule in the cloud, so the app's data
(live scores, fixtures, news) stays fresh **even when your PC is off**. The
app already auto-refreshes every 60s, so it picks up each new push on its own.

The workflow is already in the repo: [.github/workflows/push-snapshot.yml](../.github/workflows/push-snapshot.yml).
You just need to put the project on GitHub and add three secrets.

## One-time setup

### 1. Put the project on GitHub

From the project root (`c:\NJS\sports-model`):

```bash
git init
git add .
git commit -m "TrueOdds: app + backend + cloud push"
```

Create a new repo on github.com (empty, no README), then:

```bash
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

> The 26 MB `data/sports.db` is committed on purpose — the cloud job needs it
> to compute ratings. Your `.env` is **not** committed (it's git-ignored);
> secrets go in GitHub instead (next step).

**Public vs private repo:** GitHub Actions minutes are **free and unlimited on
public repos**. On private repos you get ~2,000 min/month — a 15-min cron would
exceed that, so either make the repo public or widen the interval (see below).

### 2. Add the secrets

On GitHub: **Settings → Secrets and variables → Actions → New repository secret.**
Add these three (same values as your local `.env`):

| Name | Value |
|------|-------|
| `SUPABASE_URL` | your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | the **service_role** key |
| `FOOTBALL_DATA_API_KEY` | your football-data.org key |

> The service key is write-access — keeping it in GitHub Secrets (not in code)
> is exactly why it's a secret.

### 3. Turn it on / test it

- Go to the **Actions** tab → enable workflows if prompted.
- Open **Push snapshot** → **Run workflow** to trigger it once by hand.
- It should finish green in a couple of minutes. Open the app and pull to
  refresh — newest data.
- After that it runs automatically every 15 minutes.

## Changing how often it runs

Edit the `cron` line in the workflow:

```yaml
- cron: "*/15 * * * *"   # every 15 min
# - cron: "*/30 * * * *" # every 30 min (lighter; good for private repos)
# - cron: "*/10 * * * *" # every 10 min (more "live")
```

GitHub's scheduler can delay runs a few minutes under load — that's normal.

## Good to know

- **Scheduled workflows pause after 60 days of no repo activity.** A single
  push/commit re-arms them. (Cosmetic commits or the occasional manual run keep
  it alive.)
- **Refreshing ratings:** the committed DB only changes when you re-ingest
  locally and `git push` the updated `data/sports.db`. Live fixtures/scores/news
  refresh every run regardless — they come from the APIs at push time.
- **Local option still works:** `scripts/push_snapshot.bat` + Windows Task
  Scheduler if you ever want a local runner too.
