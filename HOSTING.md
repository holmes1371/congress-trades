# Hosting the Congressional Trade Intelligence Site

## Overview

This project can be published as a public website using **GitHub Pages** with
**GitHub Actions** for automated updates.  The pipeline runs on a schedule,
generates a fresh report via the Claude API for prose commentary, and deploys
the result — zero ongoing maintenance required.

## Architecture

```
GitHub Actions (cron: weekdays 7 AM ET)
  │
  ├── run_pipeline.py       ← fetch trades, compute stats, build skeleton
  ├── auto_fill.py          ← call Claude API to write prose fills
  ├── fill_skeleton.py      ← inject prose into skeleton
  ├── generate_report.py    ← render final HTML report
  └── build_site.py         ← build index.html + copy reports → site/
        │
        └── Deploy to GitHub Pages
```

## Setup Steps

### 1. Create a GitHub repository

```bash
cd "Congressional Stock Trading Analysis"
git init
git add .
git commit -m "Initial commit"
```

Create a new repo on GitHub (e.g., `congress-trades`) and push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/congress-trades.git
git branch -M main
git push -u origin main
```

### 2. Add your Anthropic API key as a secret

The `auto_fill.py` script calls the Claude API to generate prose commentary.

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your Anthropic API key (starts with `sk-ant-...`)

### 3. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Under **Source**, select **GitHub Actions**
3. Save

### 4. Trigger the first build

Either wait for the scheduled run (weekdays at 7 AM ET), or:

1. Go to **Actions** → **Update Congressional Trade Report**
2. Click **Run workflow** → **Run workflow**

The site will be live at `https://YOUR_USERNAME.github.io/congress-trades/`
within a few minutes.

### 5. (Optional) Custom domain

To use a custom domain like `congresstrades.com`:

1. Buy the domain from any registrar (~$12/year)
2. In your repo → **Settings** → **Pages** → **Custom domain**, enter the domain
3. Add a CNAME record with your registrar pointing to `YOUR_USERNAME.github.io`
4. GitHub will auto-provision HTTPS via Let's Encrypt

## Files Added for Hosting

| File | Purpose |
|------|---------|
| `auto_fill.py` | Calls Claude API to generate `fills.json` from pipeline digest |
| `build_site.py` | Generates `site/index.html` landing page with report archive |
| `.github/workflows/update-report.yml` | GitHub Actions workflow (scheduled + manual) |
| `HOSTING.md` | This file |

## Cost Estimate

- **GitHub Pages hosting**: Free
- **GitHub Actions**: Free (2,000 minutes/month on free tier; each run ~3 min)
- **Claude API** (Sonnet): ~$0.02–0.05 per run for fills generation
- **Custom domain** (optional): ~$12/year

Total: effectively free, or ~$1/year with API costs.

## Schedule

The workflow runs weekdays at 7 AM Eastern.  If no new trades are found,
the pipeline exits early and the site is not updated (saves API costs).

To change the schedule, edit the `cron` line in
`.github/workflows/update-report.yml`.

## .gitignore Recommendations

Add a `.gitignore` to keep the repo clean:

```
__pycache__/
*.pyc
.idea/
scoring/cache/
site/
digest.txt
```

The `site/` directory is built fresh by GitHub Actions — no need to commit it.
The scoring cache is large and not needed for the report pipeline.
