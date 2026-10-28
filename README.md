# Preflight &mdash; AI-Powered Brand Compliance Checker

A modern web application for checking marketing copy, press announcements, and visual creatives against customized brand rules, tone guidelines, and **PDF-based brand guidelines** using **Google Gemini** through a **Python FastAPI** backend and **SQLite** persistence.

---

## Capabilities Overview

1. **Dashboard (Dual-Mode Content & Creative Checker)**:
   - **Marketing Copy Tab**: Pastes text and audits against active approved rules and general compliance standards (FTC claims, competitor disparagement, jargon).
   - **Creative Image Tab**: Uploads PNG, JPG, or JPEG display creatives (up to 5 MB) and renders a live image preview. Uses Gemini multimodal capabilities to inspect visible typography, slogans, unverified guarantees, aggressive tone, and basic visual consistency. Uncertain claims are marked for human review.
2. **Brand Guidelines (PDF Extraction & Approval Workflow)**:
   - Exclusively for extracting brand rules from company guideline documents.
   - 5 MB file size limit with text extraction via `pdfplumber` (rejects image-only/scanned PDFs without fake OCR).
   - Extracted rules are **never activated automatically**; admins can edit, reject, or approve & activate them.
3. **Manual Brand Rules**:
   - Create custom rules manually with rule types (`Banned Words`, `Required Words`, `Tone`, `Factual Claim`, `Other`) and severities (`Low`, `Medium`, `High`).
4. **Persistent Review History (SQLite)**:
   - Every completed text or creative audit is saved with a unique ID, timestamp, findings list, and status.

---

## Prerequisites & Installation

### 1. Install Backend Dependencies
In your terminal, navigate to the `backend` folder:
```powershell
cd C:\Users\nisha\OneDrive\Documents\PreFlight\backend
pip install -r requirements.txt
```
*(Dependencies: `fastapi`, `uvicorn`, `google-genai`, `pdfplumber`, `pillow`, `python-multipart`, `pydantic`, `python-dotenv`)*.

### 2. Verify Your Gemini API Key
Make sure your Gemini API key is configured in [`backend/.env`](file:///C:/Users/nisha/OneDrive/Documents/PreFlight/backend/.env):
```env
GEMINI_API_KEY=AIzaSy...
PORT=8000
HOST=0.0.0.0
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GEMINI_MODEL=gemini-3.8-flash
```

---

## How to Run the Application Locally

### Step 1: Start the FastAPI Backend
Open a terminal (PowerShell or Command Prompt):
```powershell
cd C:\Users\nisha\OneDrive\Documents\PreFlight\backend
python -m uvicorn main:app --reload --port 8000
```
Backend health check is accessible at `http://localhost:8000/`.

### Step 2: Start the React Frontend
Open a second terminal window:
```powershell
cd C:\Users\nisha\OneDrive\Documents\PreFlight
npm run dev
```
Open your browser and navigate to:
```text
http://localhost:5173
```

---

## How to Test Image Brand-Compliance Checking End-to-End

1. Open `http://localhost:5173`.
2. On the **Dashboard**, toggle to the **Creative Image** mode using the switch in the top right.
3. **Upload an Image Creative**:
   - Drag and drop or click to upload any PNG or JPG creative (e.g. [`backend/test_creative_ad.png`](file:///C:/Users/nisha/OneDrive/Documents/PreFlight/backend/test_creative_ad.png)).
   - Verify the image preview, filename, and file size are displayed.
4. **Audit the Creative**:
   - Click **Check Creative Image**.
   - Gemini evaluates the image against your approved rules and returns structured findings showing:
     - The visual excerpt observed in the image
     - Policy category and severity
     - Clear explanation and recommended creative adjustment
     - "Requires Human Verification" badge for tone or claims needing human sign-off
5. **Verify Review History**:
   - Click **Review History** in the sidebar.
   - Note that the image audit report is recorded in SQLite and can be viewed or reloaded at any time.
