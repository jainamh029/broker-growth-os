# Deploying

> All data in this project is synthetic. Do not attempt deployment from an automated session; follow these steps yourself. Nothing here has been run for you.

## 1. Check locally first

```bash
make setup
make all
make test
make dashboard      # confirm the banner "Synthetic data. Demonstrates the method, not Hedge's actual performance." shows on every view
```

## 2. Push to GitHub

1. Create an empty repository on GitHub (for example `broker-growth-os`). Public is fine; the repo contains only synthetic data and no secrets.
2. Confirm no secrets are tracked: `git ls-files | grep -iE "\.env|secret|key" || echo clean`.
3. Connect and push:

```bash
git remote add origin git@github.com:<your-username>/broker-growth-os.git
git branch -M main
git push -u origin main
```

`data/`, `outputs/` and `.venv/` are git-ignored on purpose. The dashboard generates its own synthetic data on first load.

## 3. Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** (or **New app**) and choose **Deploy a public app from GitHub**.
3. Repository: `<your-username>/broker-growth-os`. Branch: `main`. Main file path: `app/dashboard.py`.
4. Open **Advanced settings** and choose **Python 3.12**. Leave **Secrets** empty: nothing needs an API key.
5. Click **Deploy**. The first load takes about a minute because `app/dashboard.py` runs the seeded pipeline when `data/marts` is missing; later loads are instant.
6. Open the app URL and click through all nine views. Check the banner and the SIMULATED label on the Experiments view.
7. Paste the URL into your Loom description and README (the screenshots section).

## Troubleshooting

- **Build fails on a package version**: `requirements.txt` pins versions that need Python 3.11+. Re-deploy with Python 3.12.
- **"Missing data mart" error**: the first-run generation did not finish; reboot the app from the Streamlit menu.
- **You want the real LLM layer**: set `ANTHROPIC_API_KEY` and `BGOS_LLM_MODEL` in the app's Secrets and add `anthropic` to `requirements.txt`. The dashboard does not need it; it only affects `src/bgos/ai/`. Drafts still require human review.
