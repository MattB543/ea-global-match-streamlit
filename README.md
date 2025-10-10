# 🤝 EA Global Meeting Matcher - Streamlit Web App

A mobile-friendly, **password-protected** web interface for generating personalized EA Global meeting recommendations using Gemini Pro 2.5.

## 🔒 Security Features

✅ **Password Protection** - Access controlled via environment variable
✅ **No Data in Repo** - CSV pulled from Google Sheets URL (not committed)
✅ **Dynamic Generation** - output.md regenerated on each session from live data
✅ **Public Repo Safe** - Code can be public, data and access remain private

---

## Features

✅ **Mobile-Optimized UI** - Works perfectly on phones
✅ **Fuzzy Name Search** - Find profiles even with typos
✅ **Custom Profiles** - Can paste your own profile if not in CSV
✅ **AI-Powered Matching** - Uses 3 parallel Gemini calls with different temperatures for best results
✅ **Copy-to-Clipboard** - Easy sharing via Slack/text
✅ **Download Options** - Save as Markdown or Slack format

---

## 🚀 Quick Deploy to Streamlit Cloud (5 minutes)

### Step 1: Push to GitHub

```bash
cd streamlit_app
git init
git add .
git commit -m "EA Global matcher app"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

**Note:** You do NOT need to include `attendees.csv` or `output.md` in your repo! The app pulls data from Google Sheets.

### Step 2: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select: your repo → main → app.py
4. Click "Deploy"

### Step 3: Configure Secrets

In Streamlit Cloud dashboard → Settings → Secrets, add:

```toml
# Your Gemini API key
GEMINI_API_KEY = "your-actual-gemini-api-key"

# Google Sheets URL (full URL with /d/SHEET_ID/)
CSV_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"

# Password to access the app (choose a strong password!)
APP_PASSWORD = "your-secure-password-123"
```

**Done!** Your app will be live at `https://yourusername-repo.streamlit.app`

---

## 🔑 Getting API Keys & URLs

### Gemini API Key
1. Go to https://aistudio.google.com/app/apikey
2. Create or select a project
3. Generate API key

### Google Sheets URL
1. Open your Google Sheet
2. Copy the full URL (should look like: `https://docs.google.com/spreadsheets/d/1abc123.../edit`)
3. Make sure the sheet is set to "Anyone with the link can view"

### App Password
- Choose any secure password
- This will be required to access the app
- Share only with authorized users

---

## 🏠 Local Development

### Prerequisites

- Python 3.9+
- Gemini API key

### Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure secrets:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Then edit `.streamlit/secrets.toml` and add your values:
   ```toml
   GEMINI_API_KEY = "your-key"
   CSV_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
   APP_PASSWORD = "your-password"
   ```

3. **Run locally:**
   ```bash
   streamlit run app.py
   ```

4. **Open in browser:** http://localhost:8501

5. **Enter password** to unlock the app

---

## 🔐 How Security Works

### 1. Password Protection
- User must enter correct password before accessing any features
- Password stored in environment variable (never in code)
- Session-based authentication

### 2. No Data in Repository
- `attendees.csv` is pulled from Google Sheets URL at runtime
- `output.md` is generated dynamically from the CSV
- No sensitive attendee data committed to repo

### 3. Environment Variables
All sensitive config stored as secrets:
- `GEMINI_API_KEY` - For AI API access
- `CSV_URL` - Google Sheets URL
- `APP_PASSWORD` - Access password

### 4. Public Repo, Private Data
- Code can be open source
- Data remains private in Google Sheets
- Access controlled by password
- No credentials in code

---

## 📱 Mobile Usage

1. Open the deployed URL on your phone
2. Bookmark to home screen for app-like experience
3. Enter password to unlock
4. Search → Select → Generate → Copy/Share

**First load:** App downloads CSV and generates profiles (~5-10 seconds)
**After that:** Instant access (cached in session)

---

## 🔄 How Data Updates Work

### On Each Session Start:
1. App downloads latest CSV from Google Sheets URL
2. Filters attendees (keeps only profiles with ≥300 characters)
3. Generates output.md content in memory
4. Caches for the session

### To Update Data:
1. Edit your Google Sheet
2. Refresh the app (or start new session)
3. New data is automatically pulled

**No redeployment needed!**

---

## 🐛 Troubleshooting

### "Missing configuration" error
- Ensure all 3 secrets are set: `GEMINI_API_KEY`, `CSV_URL`, `APP_PASSWORD`
- In Streamlit Cloud: Settings → Secrets
- Locally: `.streamlit/secrets.toml`

### "Failed to load CSV" error
- Check that `CSV_URL` is correct (full Google Sheets URL)
- Ensure sheet is set to "Anyone with link can view"
- Try opening the export URL in browser: `https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/export?format=csv`

### "Incorrect password" error
- Check that `APP_PASSWORD` matches what you configured
- Passwords are case-sensitive
- No extra spaces

### App is slow
- First load: 5-10 seconds (downloads data, generates profiles)
- Recommendation generation: 30-60 seconds (3 parallel AI calls + consolidation)
- Subsequent loads: Instant (data cached in session)

### Cold starts on free tier
- Streamlit Community Cloud: **No cold starts** ✅
- Render free tier: ~30s cold start after 15 min idle
- Railway: No cold starts but limited free credit

---

## 🎯 Deployment Comparison

| Platform | Free? | Cold Starts? | Setup Time | Best For |
|----------|-------|--------------|------------|----------|
| **Streamlit Cloud** | ✅ Yes | ❌ No | 5 min | **RECOMMENDED** |
| Railway | 💵 $5 credit | ❌ No | 10 min | Quick tests |
| Render | ✅ Yes | ⚠️ Yes | 10 min | Backup option |
| DigitalOcean | 💵 $5/mo | ❌ No | 15 min | Production |

---

## 📊 Architecture

```
User → [Password Check] → Main App

Main App Flow:
1. Download CSV from Google Sheets URL
2. Generate output.md content (filter by 300+ chars)
3. Cache both in session state
4. User searches for their name
5. Fuzzy match → select profile
6. Click Generate → Create prompt with their profile + all profiles
7. Send to Gemini (3 parallel calls: temps 0, 0.75, 1.5)
8. Consolidate results → final top 10 recommendations
9. Display + save (Markdown & Slack formats)
```

**No Files Required:**
- `attendees.csv` - Downloaded from Google Sheets
- `output.md` - Generated dynamically in memory

**Only Code in Repo:**
- `app.py` - Streamlit UI
- `utils.py` - Core functions
- `requirements.txt` - Dependencies
- `.gitignore` - Excludes secrets

---

## 🔒 Security Best Practices

### ✅ DO:
- Store all secrets in environment variables
- Use strong, unique password for `APP_PASSWORD`
- Set Google Sheet to "Anyone with link" (read-only)
- Keep `.streamlit/secrets.toml` in `.gitignore`

### ❌ DON'T:
- Commit secrets to git
- Share `APP_PASSWORD` publicly
- Make Google Sheet editable by link
- Hardcode sensitive values in code

---

## 📝 Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSy...` |
| `CSV_URL` | Google Sheets URL | `https://docs.google.com/spreadsheets/d/1abc.../edit` |
| `APP_PASSWORD` | Access password | `my-secure-pass-123` |

---

## 🆘 Support

### Common Issues:

**Q: Can I use a different CSV source?**
A: Yes! Just update the `load_csv_from_url()` function in `utils.py` to support your format.

**Q: How do I change the 300 character filter?**
A: Edit the `min_chars=300` parameter in `app.py` line ~125, or make it configurable via secrets.

**Q: Can I disable password protection?**
A: Yes, but not recommended. Comment out the password check in `main()` function.

**Q: How much does this cost?**
A:
- Streamlit Cloud: FREE
- Gemini API: ~$0.01 per recommendation (4 API calls)
- Total: Virtually free for personal use

---

## 📞 Access from Phone (Local Dev)

### Option 1: Same WiFi
```bash
# Find your local IP
# Windows: ipconfig
# Mac/Linux: ifconfig

# Run with external IP
streamlit run app.py --server.address=0.0.0.0

# Access from phone: http://YOUR_LOCAL_IP:8501
```

### Option 2: ngrok (easier)
```bash
# Install: https://ngrok.com
ngrok http 8501

# Use the https URL on your phone
```

---

## ✅ Deployment Checklist

- [ ] Get Gemini API key
- [ ] Ensure Google Sheet is "view by link"
- [ ] Choose strong APP_PASSWORD
- [ ] Push code to GitHub (no CSV/output.md needed!)
- [ ] Deploy to Streamlit Cloud
- [ ] Add 3 secrets in dashboard
- [ ] Test password access
- [ ] Test on mobile
- [ ] Share password with authorized users only

**Total time:** 10-15 minutes 🚀

---

## 🎉 What's Different From Standard Setup?

### Old Way (Insecure):
❌ CSV file committed to repo
❌ output.md file in repo (contains all attendee data)
❌ No access control
❌ Can't make repo public

### New Way (Secure): ✅
✅ CSV pulled from Google Sheets (not in repo)
✅ output.md generated dynamically (not in repo)
✅ Password-protected access
✅ **Safe to make repo public!**
✅ Data stays fresh (always pulls latest from Sheets)
✅ Easy to update (just edit Google Sheet)

---

For more details, see `QUICKSTART.md`
