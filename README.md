# Project JARVIS (Streamlit + Aiven MySQL)

One Streamlit app is both frontend and backend. It talks directly to Aiven MySQL and the Gemini API. There is no FastAPI, AWS, JWT or separate server.

```
app.py            UI and page routing
jarvis/           db.py (Aiven) · repo.py (SQL) · auth.py · security.py (scrypt)
                  extract.py (PDF/PPTX/OCR) · ai.py (Gemini REST + redaction)
                  pipeline.py · quiz_parser.py
schema.sql        tables, created automatically on first start
packages.txt      apt packages for Streamlit Cloud (tesseract, poppler)
```

**Python dependencies: 3** (`streamlit`, `PyMySQL`, `pypdf`). Removed: fastapi, uvicorn, SQLAlchemy, pydantic-settings, python-jose, bcrypt, google-genai, python-multipart, pdf2image, pytesseract, Pillow, python-pptx.

## Run locally
```bash
pip install -r requirements.txt
sudo apt install tesseract-ocr poppler-utils     # only needed for scanned PDFs/images
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this folder to GitHub (`secrets.toml` is git-ignored).
2. New app → main file `app.py`. `packages.txt` installs the OCR tools.
3. App settings → Secrets: paste your filled-in `secrets.toml.example`.
4. In Aiven, allow the app's access (Aiven console → service → Allowed IP addresses). Streamlit Cloud has no fixed IP, so you will probably need `0.0.0.0/0`; the TLS CA check and strong DB password are then your protection.

## Aiven setup
Create an Aiven for MySQL service. Copy host, port, user and password. Download the **CA certificate** and paste its contents into `DB_SSL_CA`. The app creates its tables itself.
First admin: put your email in `ADMIN_EMAILS` and **register that account right after deploying** (anyone who registers a listed email first becomes admin). Other accounts are always plain users.

## Behaviour changes vs the old version
- **Login is per browser tab** (`st.session_state`). Refreshing the page signs you out. Deactivating an account takes effect on its next click. JWTs and the `user_sessions` table are gone.
- **Passwords use stdlib scrypt**, not bcrypt, so **old bcrypt hashes will not work**. Start with a fresh database, or users must re-register.
- **Quizzes are now scored**, server-side, and attempts are saved. Correct answers are never sent to the browser before submitting.
- **Uploads are processed one file at a time** in memory or a throwaway temp dir. Limits: 10 files, 40 MB combined, 20 MB each.
- Fixed a bug: the old email-redaction regex only matched uppercase addresses.
- Login throttle: 5 failures per email per 15 minutes (in-memory, resets on app restart).

## Caveats
Redaction is heuristic. Don't upload sensitive documents. Free Streamlit Cloud apps sleep when idle, and the app holds no state outside the database. DB connection is TLS with certificate-chain verification (`DB_SSL_VERIFY_HOSTNAME=true` also checks the hostname).

**Not tested against live services**: I couldn't install Streamlit/PyMySQL in my sandbox, nor reach Aiven or Gemini. Verified: unit tests (`python -m unittest discover -s tests -t .`), compilation, and real tesseract/pdftoppm OCR of an image and a scanned PDF. Run through register → login → upload → notes → quiz once on staging.
