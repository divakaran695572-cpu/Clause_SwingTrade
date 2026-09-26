# Swing Screener - phone app

A private web app you add to your phone's home screen. It runs your global 1-2 month swing-trade screen
(Danelfin AI Scores + live web research by Claude) and shows a ranked list with entry, stop and target.

- Tap **Run now** any time.
- Runs automatically Monday-Friday at **09:05 Berlin** (Xetra open) and **16:10 New York** (US close, about 22:10 Berlin).
  Daylight-saving changes are handled automatically.
- Everything (app, schedule, history) lives in ONE Render service.

Research tool only. Not financial advice.

---

## Setup (about 20 minutes)

### 1. Put the code on GitHub
1. Go to github.com and click **New repository**. Name it `swing-screener`, choose **Private**, click **Create**.
2. On the new repo page click **uploading an existing file**.
3. Unzip this project on your PC. Open the `swing-screener` folder and drag **everything inside it**
   (the `app` folder, the `static` folder, `render.yaml`, `requirements.txt`, and the other files) into the browser.
   The `app` and `static` folders must stay as folders.
4. Click **Commit changes**.

### 2. Get an Anthropic API key (pays for each run)
1. Go to console.anthropic.com, sign in, open **API keys**, click **Create key**, copy it.
2. Open **Billing**, add a little credit (for example $10), and set a **monthly spend limit**.
   This is separate from your Claude Pro subscription.

### 3. Deploy on Render
1. Go to dashboard.render.com, click **New +**, then **Blueprint**.
2. Connect your GitHub account and choose the `swing-screener` repo. Render reads `render.yaml`.
3. Fill in the three secret values when asked:
   - `ANTHROPIC_API_KEY` - the key from step 2
   - `DANELFIN_API_KEY` - your Danelfin key
   - `APP_PASSWORD` - a long password you choose (this is what you type on your phone)
4. Click **Apply**. Wait a few minutes until the service shows **Live**.
   The Starter plan (about $7/month, check Render's pricing page) is required. Free plans go to sleep,
   which would skip the scheduled runs.

### 4. Test it safely first
1. In Render open the service, then **Environment**, set `MOCK_MODE` to `true`, and save.
2. Open your app URL (shown at the top of the service page, ends with `.onrender.com`) on your phone.
3. Log in with your password and tap **Run now**. Sample data appears in a few seconds and costs nothing.
4. Set `MOCK_MODE` back to `false` and save. Then tap **Run now** for the first real run (3-10 minutes).

### 5. Install on your phone
- **iPhone (Safari):** Share button, then **Add to Home Screen**.
- **Android (Chrome):** menu (three dots), then **Install app** / **Add to Home screen**.

---

## Costs to expect
- Render Starter plan plus a 1 GB disk: about $7-8 per month.
- Anthropic API: web search costs $10 per 1,000 searches, so a run with the default limit of 30 searches is
  at most about $0.30 in search fees, plus token charges that depend on the model. About 44 scheduled runs a month
  plus manual runs adds up, so watch the usage page in the Anthropic console for the first few days and keep
  your monthly spend limit set. To spend less, lower `MAX_WEB_SEARCHES`, use a cheaper `MODEL`, or turn off one
  schedule by moving its time (see settings).
- Danelfin free plan: 500 calls a month. The screen is told to use at most 10 per run. If you run out,
  the screen continues without Danelfin data and says so in the market note.

## Settings you can change in Render (Environment tab)
| Name | What it does | Default |
|---|---|---|
| `MODEL` | Which Claude model runs the screen | `claude-sonnet-5` |
| `MAX_WEB_SEARCHES` | Web searches allowed per run | 30 |
| `MAX_DANELFIN_CALLS` | Danelfin calls the screen may use per run | 10 |
| `MAX_MANUAL_RUNS_PER_DAY` | Safety cap on the Run now button | 6 |
| `EU_RUN_TIME` / `EU_RUN_TZ` | European run | 09:05 / Europe/Berlin |
| `US_RUN_TIME` / `US_RUN_TZ` | US run | 16:10 / America/New_York |
| `SCHEDULE_ENABLED` | Turn automatic runs on or off | true |
| `WEB_SEARCH_TOOL` | Web search tool version (advanced) | web_search_20250305 |

## Changing the strategy
The screening instructions are in `app/prompt.py`. Edit that file on GitHub (pencil icon); Render redeploys automatically.

## If something goes wrong
- **Run shows "failed":** open History and read the error. Common causes: no API credit, wrong key,
  or a model name that is not available on your account (change `MODEL`).
- **Run cut off / could not read result:** raise `MAX_TOKENS` or lower `MAX_WEB_SEARCHES`.
- **No scheduled runs:** the plan must be Starter or higher, and the service must be Live.
  Holidays are not skipped; the screen still runs.
- **Forgot the password:** change `APP_PASSWORD` in Render and save.

## Security notes
- API keys live only in Render's environment settings, never in the code or on the phone.
- The app needs the password for everything except the login page.
- Anyone with the password can spend your API credit, so keep it private and keep the monthly limit on.

## Run it on your own PC (optional)
```
pip install -r requirements.txt
set MOCK_MODE=true
set APP_PASSWORD=test
uvicorn app.main:app --port 8000
```
Then open http://localhost:8000
