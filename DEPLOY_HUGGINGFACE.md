# Deploying to Hugging Face Spaces (100% Free Gradio SDK)

Hugging Face requires a credit card / billing setup for the Docker SDK to deter spam. However, the **Gradio SDK is 100% completely free with NO credit card required**!

We have configured the application so that it runs seamlessly under the **Gradio SDK**:
- Gradio runs our root [`app.py`](file:///mnt/extra/morningstar/Gradebuddy/job_search_automation/app.py).
- [`app.py`](file:///mnt/extra/morningstar/Gradebuddy/job_search_automation/app.py) downloads and verifies Playwright Chromium into the user cache on boot.
- Linux browser libraries are installed via [`packages.txt`](file:///mnt/extra/morningstar/Gradebuddy/job_search_automation/packages.txt).
- The FastAPI backend handles all `/api` routes and directly serves your compiled React application at `/`.

---

### Step 1: Create a New Space on Hugging Face
1. Go to: **[https://huggingface.co/new-space](https://huggingface.co/new-space)**
2. Enter your Space name (e.g., `job-search-automation`).
3. Select **Space SDK**: **Gradio** (100% Free, No Credit Card!).
4. Space hardware: **Free (2 vCPU · 16 GB RAM)**.
5. Set **Visibility**: **Private** 🔒
   > ⚠️ **Important:** Keep your Space Private to protect your resume, credentials, and job history.
6. Click **Create Space**.

---

### Step 2: Push the Code to Hugging Face

#### Option A: Clone the Space and Copy Files (Easiest)
```bash
# 1. Clone your newly created space
git clone https://huggingface.co/spaces/<YOUR_HF_USERNAME>/<SPACE_NAME> hf_space
cd hf_space

# 2. Copy the project files (safely excluding databases and credentials)
rsync -av --exclude='.venv' \
          --exclude='node_modules' \
          --exclude='web/frontend/node_modules' \
          --exclude='data/*.db*' \
          --exclude='data/*.key' \
          --exclude='data/indeed_*' \
          --exclude='rootkey.csv' \
          --exclude='.git' \
          /mnt/extra/morningstar/Gradebuddy/job_search_automation/ .

# 3. Commit and push
git add .
git commit -m "Deploy Job Search Automation on Gradio SDK"
git push
```

#### Option B: Push Directly via Git Remote
```bash
cd /mnt/extra/morningstar/Gradebuddy/job_search_automation

# Check or initialize git
git init
git remote add hf https://huggingface.co/spaces/<YOUR_HF_USERNAME>/<SPACE_NAME>

# Add files (protected by our .gitignore)
git add app.py packages.txt requirements.txt README.md core/ adapters/ web/ package.json .gitignore
git commit -m "Deploy to Hugging Face Spaces"
git push --force hf main
```

---

### Step 3: Add Secrets (Optional)
In your Space dashboard:
1. Click **Settings** -> **Variables and secrets**.
2. Add your AI API keys as **Secrets**:
   - `GEMINI_API_KEY`
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`

---

### Step 4: Access Your Application
Once Hugging Face finishes installing packages and shows **Running**:
* The Space will render your full React application with chat, live search, and resume tailoring.
* You can also open the full-screen direct URL:
  `https://<YOUR_HF_USERNAME>-<SPACE_NAME>.hf.space`
