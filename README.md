# Library Management System
 Done by: Mahmood AL Maawali
 Topic: Library Management System  

---

## Project Description

A Python-based mini-application that manages a library's books, members, and loans.  
It demonstrates:

| Component | Technology |
|-----------|------------|
| Database | SQLite (2 tables + loans with FK) |
| Data export | CSV |
| API output | JSON (Open Library API) |
| Data analysis | pandas DataFrames |
| Version control | Git (feature branches, PRs) |
| Error handling | try/except + custom exceptions |
| Observability | Python `logging` module |
| Profiling | cProfile + pstats |

---

## Project Structure

```
library_management/
├── library_app.py      ← main application (Parts A–G)
├── README.md
├── data/
│   └── library.db      ← SQLite database (auto-created)
├── exports/
│   ├── books_export.csv ← Part D: CSV export
│   └── api_books.json   ← Part E: JSON API output
└── logs/
    └── library.log      ← Part G: log file
```

---

## How to Run

### 1. Install dependencies

```bash
pip install requests pandas
```

### 2. Run the application

```bash
cd library_management
python library_app.py
```

### 3. Expected output

- Console output with all query results  
- `data/library.db` — SQLite database file  
- `exports/books_export.csv` — exported book data  
- `exports/api_books.json` — live API results  
- `logs/library.log` — full execution log  

---

## Database Schema

```
members                         books
──────────────────────          ──────────────────────────────
member_id  PK AUTOINCREMENT     book_id     PK AUTOINCREMENT
full_name  TEXT NOT NULL        title       TEXT NOT NULL
email      TEXT UNIQUE          author      TEXT NOT NULL
joined_date TEXT                genre       TEXT
is_active  INTEGER DEFAULT 1    year        INTEGER
                                total_copies INTEGER
                                available   INTEGER

loans  (links members ↔ books via FK)
──────────────────────────────────────────
loan_id      PK
member_id    FK → members.member_id
book_id      FK → books.book_id
loan_date    TEXT
due_date     TEXT
return_date  TEXT (NULL if not yet returned)
```

---

## API Used

**Open Library Search API** — `https://openlibrary.org/search.json`  
- Free, no authentication required  
- Returns books with title, author, year, and subject  

---

## Part F – Debugging Report

| # | Bug | Where | Root Cause | Fix |
|---|-----|--------|------------|-----|
| 1 | Due date was same as loan date | `issue_book()` | `timedelta(days=0)` instead of `days=14` | Changed to `timedelta(days=14)` |
| 2 | SQL column typo `titl` | `export_books_to_csv()` | Typo in SELECT statement | Corrected to `title` |
| 3 | Mutable default argument `limit=[]` | `fetch_books_from_api()` | Python shares mutable defaults across calls | Changed to `limit: int = 5` |

---

## Git Workflow

```
main
├── feature/database    ← Parts B & C (SQLite design, CRUD, queries)
├── feature/API         ← Part E (Open Library integration + JSON)
└── feature/logging     ← Parts F & G (debugging, logging, profiling)
```

### Commit convention

| Prefix | Meaning |
|--------|---------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `refactor:` | Code restructure |
| `docs:` | Documentation |

---

## Git Setup Commands

```bash
git init
git checkout -b feature/database
# ... work on DB code ...
git add .
git commit -m "feat: initialise SQLite schema with members and books tables"
git commit -m "feat: add CRUD functions for members and books"
git commit -m "feat: add two logical-operator queries"
git checkout main && git merge feature/database

git checkout -b feature/API
git commit -m "feat: integrate Open Library API with error handling"
git commit -m "feat: add JSON output for API results"
git checkout main && git merge feature/API

git checkout -b feature/logging
git commit -m "feat: add logging module with file and console handlers"
git commit -m "fix: resolve 3 intentional bugs with debug documentation"
git commit -m "refactor: replace print statements with proper logging"
git checkout main && git merge feature/logging

git remote add origin https://github.com/<your-username>/library-management.git
git push -u origin main
```

---

## Team Management

| Member | Tasks |
|--------|-------|
| Student A | Parts B, C – Database design, CRUD, queries |
| Student B | Parts E, F, G – API, debugging, logging |
| Both | Part A – Git workflow, README, integration |

---

## Learning Outcomes Covered

- **LO3** – File handling (CSV/JSON), SQLite database, API integration  
- **LO4** – Exception handling, logging, profiling, debugging  
- **LO5** – Git workflow, feature branches, collaborative development  
