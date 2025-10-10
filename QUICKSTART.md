# ⚡ Quick Start Guide - Secure Version

## 🔒 Key Security Features

✅ **Password-protected** - Only authorized users can access
✅ **No data in repo** - CSV pulled from Google Sheets
✅ **Dynamic generation** - output.md created on-the-fly
✅ **Public repo safe** - Code can be open source

---

## ☁️ Deploy to Streamlit Cloud (5 minutes) - RECOMMENDED

```bash
# 1. Push to GitHub (NO CSV or output.md needed!)
cd streamlit_app
git init
git add .
git commit -m "EA Global matcher (secure)"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main

# 2. Deploy
# Go to: https://share.streamlit.io
# Click: "New app" → Select your repo → main → app.py → Deploy

# 3. Add secrets (in Streamlit Cloud dashboard → Settings → Secrets)
GEMINI_API_KEY = "your-gemini-key"
CSV_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
APP_PASSWORD = "your-secure-password"

# Done! Live at: https://YOUR_USERNAME-YOUR_REPO.streamlit.app
```

---

## 🏠 Local Testing (5 minutes)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your values

# 3. Run
streamlit run app.py

# 4. Open http://localhost:8501
# 5. Enter password to unlock
```

---

## 🔑 Required Secrets (3 values)

### 1. GEMINI_API_KEY
Get from: https://aistudio.google.com/app/apikey

### 2. CSV_URL
Your Google Sheets URL (full URL with /d/SHEET_ID/)
Example: `https://docs.google.com/spreadsheets/d/1abc123.../edit`

**Important:** Set sheet to "Anyone with link can view"

### 3. APP_PASSWORD
Choose any secure password - this protects access to the app
Example: `my-secure-pass-EA2025`

---

## 📱 Using on Phone

1. Open your deployed URL
2. Enter password to unlock
3. Bookmark to home screen (app-like experience)
4. Search → Select → Generate → Copy/Share

**First load:** 5-10 seconds (downloads & processes data)
**After:** Instant (cached in session)

---

## 🔄 How It Works

```
1. User enters password → Unlock app
2. App downloads CSV from Google Sheets
3. App filters profiles (≥300 chars) → generates output.md in memory
4. User searches name → fuzzy match
5. User generates recommendations → AI analysis
6. Results ready to copy/share
```

**No files in repo needed!** All data pulled from Google Sheets on startup.

---

## 🆘 Troubleshooting

**"Missing configuration"**
- Add all 3 secrets in dashboard or secrets.toml

**"Incorrect password"**
- Check APP_PASSWORD (case-sensitive, no extra spaces)

**"Failed to load CSV"**
- Verify CSV_URL is correct
- Check Google Sheet is set to "view by link"

**App slow first time**
- Normal! Downloads & processes data (~5-10 sec)
- After first load: instant

---

## ✅ Quick Checklist

- [ ] Get Gemini API key
- [ ] Get Google Sheets URL (set to "view by link")
- [ ] Choose strong password
- [ ] Push to GitHub (**no CSV/output.md**)
- [ ] Deploy to Streamlit Cloud
- [ ] Add 3 secrets
- [ ] Test password
- [ ] Test on mobile

**Total: 10 minutes** 🚀

---

## 🎯 What's Different?

### Old Version:
- CSV and output.md in repo (data exposed)
- No password protection
- Can't make repo public

### New Version: ✅
- CSV pulled from Google Sheets (not in repo)
- output.md generated dynamically (not in repo)
- Password-protected
- **Safe to make repo public!**

---

## 📞 Share with Others

1. Give them the deployed URL
2. Share the APP_PASSWORD (privately)
3. They can use it from any device

---

**Need more details?** Check `README.md`
