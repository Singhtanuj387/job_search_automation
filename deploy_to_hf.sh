#!/usr/bin/env bash
set -e

SPACE_NAME="singht387/job-search-automation"
SPACE_URL="https://huggingface.co/spaces/${SPACE_NAME}"
TARGET_DIR="scratch/hf_space"

echo "========================================================"
echo " Deploying Job Search Automation to Hugging Face Spaces"
echo " Target Space: $SPACE_URL"
echo "========================================================"

# Prompt for token if not already in environment
if [ -z "$HF_TOKEN" ]; then
    echo "You need a Hugging Face Access Token with WRITE permissions."
    echo "Generate one here: https://huggingface.co/settings/tokens"
    echo ""
    read -sp "Enter your Hugging Face Access Token: " HF_TOKEN
    echo ""
fi

if [ -z "$HF_TOKEN" ]; then
    echo "[-] Error: Access Token cannot be empty."
    exit 1
fi

AUTH_URL="https://singht387:${HF_TOKEN}@huggingface.co/spaces/${SPACE_NAME}"

# Clean scratch clone directory if it already exists
rm -rf "$TARGET_DIR"
mkdir -p scratch

echo "[*] Cloning Space repository..."
git clone "$AUTH_URL" "$TARGET_DIR"

echo "[*] Copying project files (excluding 1GB database, caches, and credentials)..."
python3 -c "
import shutil
from pathlib import Path

src = Path('.')
dst = Path('$TARGET_DIR')

ignore_filter = shutil.ignore_patterns(
    '.venv*', 'node_modules*', '*.db*', '*.key', 'indeed_*',
    'profile_resumes*', 'materials*', 'rootkey.csv', '.git*',
    'scratch*', '__pycache__*', '*.pyc', 'results.json', 'run_report.json',
    '*.docx', '*.pdf'
)

for item in ['app.py', 'packages.txt', 'requirements.txt', 'package.json', '.gitignore', 'run_search.py', 'model.py']:
    src_file = src / item
    if src_file.exists():
        shutil.copy2(src_file, dst / item)

for folder in ['core', 'adapters', 'web']:
    src_folder = src / folder
    dst_folder = dst / folder
    if dst_folder.exists():
        shutil.rmtree(dst_folder)
    shutil.copytree(src_folder, dst_folder, ignore=ignore_filter)
"

cd "$TARGET_DIR"

echo "[*] Adding and committing files..."
git add -A
git commit -m "Deploy Job Search Automation Web App on Gradio SDK" || echo "[*] No new changes to commit"

echo "[*] Pushing to Hugging Face..."
git push origin main

echo ""
echo "========================================================"
echo " [✓] Deployment successfully pushed to Hugging Face!"
echo " Space Page: $SPACE_URL"
echo " Direct Web App: https://singht387-job-search-automation.hf.space"
echo "========================================================"
