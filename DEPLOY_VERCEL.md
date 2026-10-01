# Deploying Job Search Automation to Vercel

Vercel provides instant global edge deployment, automatic SSL, and zero-cold-start delivery for the React frontend, while connecting to your live backend (e.g. on Hugging Face Spaces or custom server).

---

## Architecture Overview

- **Frontend (Vercel)**: Fast, modern React 19 + Vite single-page application.
- **Backend (Hugging Face / VPS / Cloud)**: Stateful Python FastAPI backend that manages headless Playwright Chromium, background schedulers, AI resume tailoring, and SQLite storage.
- **API Proxying (`vercel.json`)**: Vercel automatically proxies all `/api/*` traffic directly to your backend (`https://singht387-job-search-automation.hf.space/api/*`), preventing CORS issues.

---

## Method 1: Deploy with Vercel Web Dashboard (Recommended)

1. **Push your code to GitHub** (already configured on `main` branch):
   - `https://github.com/rroshankv98-codes/Roshan-.git` or your own repository.

2. **Open Vercel**:
   - Go to [vercel.com](https://vercel.com) and log in.
   - Click **"Add New..."** &rarr; **"Project"**.

3. **Import Git Repository**:
   - Select your GitHub repository (`Roshan-` or `job_search_automation`).

4. **Configure Project Settings**:
   - **Framework Preset**: `Vite` (Auto-detected).
   - **Root Directory**: `./` (Default).
   - **Build Command**: `npm --prefix web/frontend install && npm --prefix web/frontend run build` (Pre-configured in `vercel.json` & `package.json`).
   - **Output Directory**: `web/frontend/dist` (Pre-configured in `vercel.json`).

5. **(Optional) Environment Variables**:
   If you want to point to a custom backend instead of the default proxy:
   - Key: `VITE_API_URL`
   - Value: `https://singht387-job-search-automation.hf.space` (or your custom URL)

6. **Click "Deploy"**:
   - Vercel will build the frontend in ~30 seconds and provide you with a live production URL like `https://job-search-automation-xxx.vercel.app`.

---

## Method 2: Deploy with Vercel CLI

If you have the Vercel CLI installed:

```bash
# 1. Login to Vercel
npx vercel login

# 2. Deploy preview
npx vercel

# 3. Deploy to production
npx vercel --prod
```

---

## Pre-configured Files

The project contains everything required for zero-configuration Vercel deployment:

1. **[`vercel.json`](vercel.json)**:
   - Configures the build and output directories.
   - Sets up automatic SPA routing (fallback to `index.html`).
   - Sets up edge proxying for `/api/*` to the live backend.
2. **[`package.json`](package.json)**:
   - `npm run build` installs frontend dependencies and runs `vite build`.
3. **[`web/frontend/src/api.js`](web/frontend/src/api.js)**:
   - Reads `import.meta.env.VITE_API_URL` when provided, or falls back to `/api` (proxied by Vercel) or `localhost:8000`.
