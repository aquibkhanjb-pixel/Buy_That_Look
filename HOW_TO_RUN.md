# How to Run the Fashion Recommendation System

This guide is written for **your specific environment**:
- OS: Windows 11
- Backend env: `fashion-ai` (Conda)
- Scraper env: `fashionscraperenv` (virtualenv inside `scraper/`)
- Node.js v22 / npm 11
- PostgreSQL 17 (local)

---

## Prerequisites (One-Time Setup)

Make sure the following are installed and running:
- [x] Anaconda / Conda
- [x] Node.js v22
- [x] PostgreSQL 17

---

## Step 1 — Start PostgreSQL

PostgreSQL must be running before the backend starts.

Open **Services** (press `Win + R` → type `services.msc`) and make sure **postgresql-x64-17** is running.

Or start it from the terminal:
```bash
# Start PostgreSQL service
net start postgresql-x64-17
```

---

## Step 2 — Start the Backend

Open a terminal and run:

```bash
cd "C:\Users\Aquib Khan\Desktop\Fashion_Recommendation\backend"

conda activate fashion-ai

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

Verify it's working:
```
http://localhost:8000/api/v1/health       → {"status":"healthy",...}
http://localhost:8000/docs                → Swagger API docs
```

---

## Step 3 — Start the Frontend

Open a **new terminal** (keep the backend running) and run:

```bash
cd "C:\Users\Aquib Khan\Desktop\Fashion_Recommendation\frontend"

npm run dev
```

**Expected output:**
```
▲ Next.js 14.1.0
- Local: http://localhost:3000
✓ Ready in 2.6s
```

Open your browser at: **http://localhost:3000**

---

## Summary — Two Terminals

| Terminal | Directory | Command |
|---|---|---|
| Terminal 1 | `backend/` | `conda activate fashion-ai` → `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |
| Terminal 2 | `frontend/` | `npm run dev` |

---

## Environment Files (Already Configured)

| File | Key Setting |
|---|---|
| `backend/.env` | `DATABASE_URL=postgresql://fashionuser:fashionpass@localhost:5432/fashiondb` |
| `frontend/.env` | `NEXT_PUBLIC_API_URL=http://localhost:8000` |

> Do not change these unless you move to a different machine or database.

---

## Stopping the Project

In each terminal press `Ctrl + C` to stop the server.

---

## Quick Troubleshooting

### Backend won't start — "connection refused" or DB error
- PostgreSQL is not running. Start it with `net start postgresql-x64-17`
- Or switch to SQLite for local testing by changing `backend/.env`:
  ```
  DATABASE_URL=sqlite:///./test.db
  ```

### Frontend shows "Failed to search"
- The backend is not running or crashed. Check Terminal 1.
- Confirm `frontend/.env` has `NEXT_PUBLIC_API_URL=http://localhost:8000`

### Port 3000 already in use
```bash
# Find and kill the process using port 3000
netstat -ano | findstr :3000
taskkill /PID <pid_number> /F
```

### Port 8000 already in use
```bash
netstat -ano | findstr :8000
taskkill /PID <pid_number> /F
```

### `conda activate fashion-ai` not recognized in Git Bash
Use Anaconda Prompt instead, or run:
```bash
source activate fashion-ai
```

---

## Access Points

| Service | URL |
|---|---|
| Frontend UI | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/api/v1/health |
| Trends API | http://localhost:8000/api/v1/trends/ |
