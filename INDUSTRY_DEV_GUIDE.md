# Industry Development Guide
## How to Build, Debug, and Extend a Project Like a Professional

This guide covers the real-world process used in software companies — from starting a project from scratch to fixing bugs and shipping new features safely.

---

## Part 1 — Starting a Project from Scratch

### Step 1: Requirements Before Code
Before writing a single line of code, answer these questions in writing:

- **What problem does this solve?** (1–2 sentences max)
- **Who is the user?** (persona: age, tech-savviness, device)
- **What are the core features?** (must-haves vs nice-to-haves)
- **What are the constraints?** (budget, timeline, team size, tech stack)
- **What does success look like?** (measurable: 100 users, <500ms response time)

Write this in a `PRODUCT_SPEC.md`. Revisit it every 2 weeks.

### Step 2: Design the Architecture First
Draw (or write) the system design before building:

```
User → Frontend (Next.js) → API (FastAPI) → Services (LLM, Search) → DB (PostgreSQL)
```

Decide:
- **Where does data live?** (DB tables, cache, files)
- **Who calls what?** (which service talks to which)
- **What are the external dependencies?** (APIs, SDKs — list their failure modes)
- **Synchronous or async?** (real-time vs background jobs)

Mistakes made here are 10x cheaper to fix than after building.

### Step 3: Set Up Infrastructure Before Features

In order:
1. **Git repo** with a clear branch strategy (see Part 3)
2. **Environment files** — `.env.example` committed, `.env` gitignored
3. **CI/CD pipeline** (GitHub Actions → run tests on every PR)
4. **Two environments minimum**: `development` (local) and `production` (cloud)
5. **Logging from day one** — you cannot debug what you cannot see
6. **Database migrations tool** (Alembic for SQLAlchemy) — never alter tables manually

### Step 4: Build in Vertical Slices, Not Layers
Bad approach (build all layers first):
```
Week 1: All DB models
Week 2: All API endpoints
Week 3: All frontend pages
Week 4: Connect them
```

Good approach (one working feature at a time):
```
Week 1: Login works end-to-end (DB + API + Frontend)
Week 2: Chat works end-to-end
Week 3: Wishlist works end-to-end
```

Each slice is shippable. You can show progress to stakeholders every week.

### Step 5: Define Done
A feature is not "done" when you finish coding. It is done when:
- [ ] Code written and working locally
- [ ] Tests written (at minimum: happy path + one failure case)
- [ ] Code reviewed by at least one other person (or self-reviewed after sleeping)
- [ ] Deployed to staging and tested there
- [ ] Deployed to production
- [ ] Monitored for 24h — no errors in logs

---

## Part 2 — The Bug Fix Process

### The Golden Rule
**Never fix a bug you cannot reproduce.**
Guessing the fix without seeing the bug leads to: wrong fix, new bugs, wasted time.

### Step-by-Step Bug Fix Process

#### 1. Reproduce It
- Get the exact steps to trigger the bug
- Identify: which environment (dev/staging/prod)? which user? which data?
- Reproduce it locally before touching anything

#### 2. Read the Logs First
```bash
# Backend logs
uvicorn logs / render logs

# Frontend logs
Browser DevTools → Console + Network tab
```
90% of bugs announce themselves in the logs. Read the full error, not just the last line.

#### 3. Find the Root Cause (not just the symptom)
Ask "why" 5 times:
```
Bug: User gets 500 error on login
Why? → Backend crashes
Why? → NullPointerException on user.tier
Why? → user.tier is None in DB
Why? → /users/sync didn't set default tier
Why? → Missing default value in DB column  ← ROOT CAUSE
```
Fix the root cause, not the symptom (don't just add `if tier is None: tier = "free"`).

#### 4. Write the Fix in a Branch
```bash
git checkout -b fix/login-500-null-tier
# make the fix
git commit -m "fix: set default tier='free' in users table column"
git push origin fix/login-500-null-tier
```

#### 5. Test the Fix
- Does it fix the bug? ✓
- Does it break anything else? (run existing tests, manually test related features)
- Does it handle edge cases? (empty string, None, concurrent requests)

#### 6. Deploy and Verify
Deploy → watch logs for 15 minutes → confirm the bug is gone in production.

#### 7. Write a Post-Mortem (for serious bugs)
One paragraph:
```
What happened → Why it happened → How we fixed it → How we prevent it next time
```

---

## Part 3 — Adding a New Feature

### Branch Strategy

```
main          ← always deployable, never commit here directly
  └── feature/dupe-finder        ← new feature
  └── feature/style-profile      ← another feature
  └── fix/search-badge-bug       ← bug fix
  └── chore/update-dependencies  ← maintenance
```

Rule: **main is sacred.** Every change goes through a branch + PR.

### Step-by-Step Feature Process

#### 1. Write a Mini-Spec (even for small features)
Before coding, write 10 lines answering:
- What does the user see / do?
- What does the backend do?
- What DB changes are needed?
- What can go wrong?
- How do we know it's working?

This takes 15 minutes and saves hours of rework.

#### 2. Plan the DB Changes First
If the feature needs new tables or columns:
- Write the migration script before writing any other code
- Test it on a copy of the production DB if possible
- Never use `CREATE TABLE IF NOT EXISTS` as your only migration strategy — use Alembic

#### 3. Build Backend First, Then Frontend
```
DB migration → API endpoint → Test endpoint with curl/Postman → Frontend
```

Testing the API before building the frontend means you catch logic bugs
before they get buried in UI code.

#### 4. Use Feature Flags for Big Features
If a feature takes more than 1 week to build, use a flag:
```python
DUPE_FINDER_ENABLED = os.environ.get("DUPE_FINDER_ENABLED", "false") == "true"
```
This lets you deploy partial code to production safely (flag is off)
and turn it on when ready. No long-lived branches, no merge conflicts.

#### 5. Code Review Checklist
Before merging any PR, check:
- [ ] Does it handle errors gracefully? (no unhandled exceptions reaching the user)
- [ ] Are there any security issues? (SQL injection, exposed keys, missing auth)
- [ ] Is there any sensitive data in logs? (never log passwords, tokens, PII)
- [ ] Does it work on mobile? (if it's a UI change)
- [ ] Are rate limits / abuse scenarios considered?
- [ ] Will this break existing users' data?

#### 6. Deployment Checklist
- [ ] DB migration run before deploying new code (never after)
- [ ] New environment variables added to all environments
- [ ] Old environment variables removed if no longer needed
- [ ] Tested on staging with real data
- [ ] Rollback plan ready (what's the command to revert?)

---

## Part 4 — Code Quality Rules That Save You in the Long Run

### Naming
```python
# Bad
def proc(u, d):
    ...

# Good
def send_price_alert(user: User, alert: PriceAlert):
    ...
```

### Never Suppress Errors Silently
```python
# Bad — you'll never know this failed
try:
    send_email(user)
except:
    pass

# Good
try:
    send_email(user)
except Exception as e:
    logger.error(f"Failed to send price alert email to {user.email}: {e}")
```

### Environment Variables — Never in Code
```python
# Bad
API_KEY = "sk-abc123xyz"  # never commit secrets

# Good
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY is not set")
```

### Write the Unhappy Path First
```python
def add_to_wishlist(user_id, product):
    # Check limits FIRST — before any DB writes
    if get_wishlist_count(user_id) >= FREE_LIMIT:
        raise LimitExceeded("Upgrade to add more items")

    # Happy path last
    db.add(WishlistItem(...))
```

---

## Part 5 — Monitoring (How You Know Something Is Wrong)

In industry, you find out about bugs **before users report them**.

### Minimum Monitoring Setup
1. **Error logging** — every exception is logged with full context (Loguru, Sentry)
2. **Health check endpoint** — `/health` pinged every minute by uptime monitor
3. **Uptime monitor** — UptimeRobot (free) alerts you if site goes down
4. **Key metrics to watch**:
   - API error rate (should be < 1%)
   - Response time (should be < 2s for 95% of requests)
   - DB connection pool (should never be exhausted)

### When Production Goes Down — Incident Checklist
```
1. Check uptime monitor — is it really down?
2. Check /health endpoint — is the server responding?
3. Check logs — what's the first error? When did it start?
4. Check recent deployments — did something change in last 2 hours?
5. Check external dependencies — is Gemini/Serper/DB down?
6. Rollback to last known good version if unsure
7. Fix forward only if the fix is low-risk and fast
```

---

## Part 6 — Git Commit Messages That Are Actually Useful

```bash
# Bad
git commit -m "fix stuff"
git commit -m "update"
git commit -m "wip"

# Good — type(scope): description
git commit -m "feat(dupe-finder): add Google Lens price comparison endpoint"
git commit -m "fix(chat): prevent stale closure losing backendToken in triggerRef"
git commit -m "chore(deps): remove unused torch/faiss from requirements.txt"
git commit -m "refactor(wishlist): move limit check to DB layer for consistency"
```

Types: `feat` | `fix` | `chore` | `refactor` | `docs` | `test` | `perf`

---

## Quick Reference — What to Do When

| Situation | First Action |
|-----------|-------------|
| Found a bug | Reproduce it locally before touching code |
| Adding a feature | Write a mini-spec first |
| Changing the DB | Write migration script first |
| Deploying to prod | Run DB migration BEFORE deploying code |
| Site is down | Check logs before changing anything |
| Merge conflict | Understand both changes before resolving |
| Dependency update | Update one at a time, not all at once |
| Performance is slow | Measure first, optimize second (never guess) |
| Security concern | Fix immediately, deploy out of cycle |
