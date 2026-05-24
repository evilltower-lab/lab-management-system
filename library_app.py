# ───────────────────────────────────────
# LOGGING SETUP 
# ───────────────────────────────────────
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "library.log"), mode="a"),
        logging.StreamHandler(),          # also print to console
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# STANDARD IMPORTS
# ─────────────────────────────────────────────
import sqlite3
import csv
import json
import cProfile
import pstats
import io
import requests
import pandas as pd
from datetime import date, timedelta
from typing import Optional

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DB_PATH      = os.path.join(os.path.dirname(__file__), "data", "library.db")
CSV_EXPORT   = os.path.join(os.path.dirname(__file__), "exports", "books_export.csv")
JSON_OUTPUT  = os.path.join(os.path.dirname(__file__), "exports", "api_books.json")
OPEN_LIB_URL  = "https://openlibrary.org/search.json"
GUTENDEX_URL  = "https://gutendex.com/books/"       # Project Gutenberg API (fallback)

os.makedirs(os.path.dirname(DB_PATH),    exist_ok=True)
os.makedirs(os.path.dirname(CSV_EXPORT), exist_ok=True)

# ══════════════════════════════════════════════
#  PART B – SQLITE DATABASE DESIGN
# ══════════════════════════════════════════════

def init_db() -> sqlite3.Connection:
    """Create / connect to the SQLite database and initialise tables."""
    logger.info("Initialising SQLite database at %s", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row        # allows dict-like column access
    cur = conn.cursor()

    # Table 1 – Members (Primary Key: member_id)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            member_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name   TEXT    NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            joined_date TEXT    NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Table 2 – Books (Primary Key: book_id)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            book_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            author      TEXT    NOT NULL,
            genre       TEXT,
            year        INTEGER,
            total_copies INTEGER NOT NULL DEFAULT 1,
            available   INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Table 3 – Loans (Foreign Keys → members & books)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            loan_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id   INTEGER NOT NULL,
            book_id     INTEGER NOT NULL,
            loan_date   TEXT    NOT NULL,
            due_date    TEXT    NOT NULL,
            return_date TEXT,
            FOREIGN KEY (member_id) REFERENCES members(member_id),
            FOREIGN KEY (book_id)   REFERENCES books(book_id)
        )
    """)

    conn.commit()
    logger.info("Tables created / verified successfully.")
    return conn


# ══════════════════════════════════════════════
#  PART C – CONNECTING SQLITE WITH PYTHON
# ══════════════════════════════════════════════

# ── INSERT ──────────────────────────────────

def add_member(conn: sqlite3.Connection, full_name: str, email: str) -> int:
    """Insert a new member and return the new member_id."""
    logger.info("Adding member: %s (%s)", full_name, email)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO members (full_name, email, joined_date) VALUES (?, ?, ?)",
            (full_name, email, str(date.today()))
        )
        conn.commit()
        logger.info("Member added with id=%d", cur.lastrowid)
        return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        logger.error("Failed to add member %s: %s", email, exc)
        raise


def add_book(conn: sqlite3.Connection, title: str, author: str,
             genre: str, year: int, copies: int = 1) -> int:
    """Insert a new book record."""
    logger.info("Adding book: '%s' by %s", title, author)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO books (title, author, genre, year, total_copies, available)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, author, genre, year, copies, copies)
    )
    conn.commit()
    logger.info("Book added with id=%d", cur.lastrowid)
    return cur.lastrowid


def issue_book(conn: sqlite3.Connection, member_id: int, book_id: int) -> int:
    """Issue a book to a member (creates a loan record)."""
    logger.info("Issuing book_id=%d to member_id=%d", book_id, member_id)
    cur = conn.cursor()

    # Validate availability
    cur.execute("SELECT available, title FROM books WHERE book_id = ?", (book_id,))
    row = cur.fetchone()
    if not row:
        logger.error("Book id=%d not found.", book_id)
        raise ValueError(f"Book id={book_id} does not exist.")
    if row["available"] < 1:
        logger.warning("Book '%s' is not available.", row["title"])
        raise ValueError(f"Book '{row['title']}' has no available copies.")

    loan_date = date.today()
    due_date  = loan_date + timedelta(days=14)

    cur.execute(
        """INSERT INTO loans (member_id, book_id, loan_date, due_date)
           VALUES (?, ?, ?, ?)""",
        (member_id, book_id, str(loan_date), str(due_date))
    )
    cur.execute("UPDATE books SET available = available - 1 WHERE book_id = ?", (book_id,))
    conn.commit()
    logger.info("Loan created. Due date: %s", due_date)
    return cur.lastrowid


# ── UPDATE ──────────────────────────────────

def return_book(conn: sqlite3.Connection, loan_id: int) -> None:
    """Mark a loan as returned and increment available copies."""
    logger.info("Processing return for loan_id=%d", loan_id)
    cur = conn.cursor()
    cur.execute("SELECT book_id, return_date FROM loans WHERE loan_id = ?", (loan_id,))
    row = cur.fetchone()
    if not row:
        logger.error("Loan id=%d not found.", loan_id)
        raise ValueError(f"Loan id={loan_id} does not exist.")
    if row["return_date"]:
        logger.warning("Loan %d already returned on %s.", loan_id, row["return_date"])
        return

    cur.execute(
        "UPDATE loans SET return_date = ? WHERE loan_id = ?",
        (str(date.today()), loan_id)
    )
    cur.execute(
        "UPDATE books SET available = available + 1 WHERE book_id = ?",
        (row["book_id"],)
    )
    conn.commit()
    logger.info("Book returned successfully.")


def update_member_status(conn: sqlite3.Connection, member_id: int, active: bool) -> None:
    """Activate or deactivate a member account."""
    logger.info("Updating member_id=%d active=%s", member_id, active)
    conn.execute(
        "UPDATE members SET is_active = ? WHERE member_id = ?",
        (1 if active else 0, member_id)
    )
    conn.commit()


# ── DELETE ──────────────────────────────────

def delete_member(conn: sqlite3.Connection, member_id: int) -> None:
    """Remove a member (only if no active loans)."""
    logger.info("Attempting to delete member_id=%d", member_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM loans WHERE member_id = ? AND return_date IS NULL",
        (member_id,)
    )
    if cur.fetchone()["cnt"] > 0:
        logger.error("Cannot delete member %d – active loans exist.", member_id)
        raise ValueError("Member has active loans and cannot be deleted.")
    cur.execute("DELETE FROM members WHERE member_id = ?", (member_id,))
    conn.commit()
    logger.info("Member %d deleted.", member_id)


# ── RETRIEVE + DATAFRAMES ───────────────────

def get_all_books(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all books as a DataFrame."""
    logger.info("Fetching all books.")
    df = pd.read_sql_query("SELECT * FROM books", conn)
    return df


def get_all_members(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all members as a DataFrame."""
    logger.info("Fetching all members.")
    return pd.read_sql_query("SELECT * FROM members", conn)


def get_active_loans(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all active (unreturned) loans as a DataFrame."""
    logger.info("Fetching active loans.")
    return pd.read_sql_query(
        "SELECT * FROM loans WHERE return_date IS NULL", conn
    )


# ── QUERY WITH LOGICAL OPERATORS ────────────

def search_available_books_by_genre(conn: sqlite3.Connection, genre: str) -> pd.DataFrame:
    """
    Query 1 – Uses AND logical operator:
    Find available books in a given genre.
    """
    logger.info("Searching available books in genre='%s'", genre)
    sql = """
        SELECT book_id, title, author, year, available
        FROM   books
        WHERE  genre = ? AND available > 0
        ORDER  BY title
    """
    return pd.read_sql_query(sql, conn, params=(genre,))


def get_overdue_or_missing(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Query 2 – Uses OR logical operator:
    Find loans that are overdue OR have been returned late.
    """
    logger.info("Checking overdue / late-return loans.")
    today = str(date.today())
    sql = """
        SELECT l.loan_id, m.full_name, b.title,
               l.loan_date, l.due_date, l.return_date
        FROM   loans l
        JOIN   members m ON l.member_id = m.member_id
        JOIN   books   b ON l.book_id   = b.book_id
        WHERE  (l.return_date IS NULL AND l.due_date < ?)
            OR (l.return_date IS NOT NULL AND l.return_date > l.due_date)
        ORDER  BY l.due_date
    """
    return pd.read_sql_query(sql, conn, params=(today,))


# ══════════════════════════════════════════════
#  PART D – EXPORT / IMPORT DATA
# ══════════════════════════════════════════════

def export_books_to_csv(conn: sqlite3.Connection, filepath: str = CSV_EXPORT) -> None:
    """Export three attributes (title, author, available) of all books to CSV."""
    logger.info("Exporting books to CSV: %s", filepath)
    try:
        cur = conn.cursor()
        cur.execute("SELECT title, author, available FROM books")
        rows = cur.fetchall()
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "author", "available"])
            writer.writerows(rows)
        logger.info("Exported %d rows to %s", len(rows), filepath)
    except OSError as exc:
        logger.error("CSV export failed: %s", exc)
        raise


def import_csv_to_dataframe(filepath: str = CSV_EXPORT) -> pd.DataFrame:
    """Import CSV data into a pandas DataFrame."""
    logger.info("Importing CSV from %s", filepath)
    try:
        df = pd.read_csv(filepath)
        logger.info("Imported %d records from CSV.", len(df))
        return df
    except FileNotFoundError as exc:
        logger.error("CSV file not found: %s", exc)
        raise


# ══════════════════════════════════════════════
#  PART E – API INTEGRATION (Open Library)
# ══════════════════════════════════════════════

# For demonstration, we'll use the Gutendex API (Project Gutenberg) as a fallback if Open Library is unavailable.
# Note: Open Library's search API is more complex and may require additional parameters for pagination, but Gutendex provides a simpler interface for this exercise.
def fetch_books_from_api(query: str, limit: int = 5) -> list[dict]:
    """
    Fetch books from the Gutendex (Project Gutenberg) public API.
    Falls back gracefully with error handling.
    Returns results as JSON-serialisable dicts.
    """
    logger.info("Calling Gutendex API: query='%s' limit=%d", query, limit)
    params = {"search": query, "mime_type": "text/html"}
    try:
        response = requests.get(GUTENDEX_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        logger.error("Network error – cannot reach Gutendex API.")
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP error from API: %s", exc)
        raise
    except requests.exceptions.Timeout:
        logger.error("API request timed out.")
        raise

    books = []
    for doc in data.get("results", [])[:limit]:
        authors = doc.get("authors", [])
        author_name = authors[0]["name"] if authors else "Unknown"
        subjects = doc.get("subjects", [])
        genre = subjects[0] if subjects else "General"
        book = {
            "title":  doc.get("title", "Unknown"),
            "author": author_name,
            "year":   None,          # Gutendex doesn't return year in list view
            "genre":  genre[:80],    # truncate long subject strings
        }
        books.append(book)

    logger.info("API returned %d books.", len(books))
    return books

# Store api books in the database, skipping duplicates based on title and author. This is a simple approach; in a real app, you might want a more robust deduplication strategy.
def store_api_books(conn: sqlite3.Connection, books: list[dict]) -> None:
    """Insert API-fetched books into the local database (skip duplicates)."""
    logger.info("Storing %d API books in database.", len(books))
    cur = conn.cursor()
    for b in books:
        cur.execute("SELECT 1 FROM books WHERE title = ? AND author = ?", (b["title"], b["author"]))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO books (title, author, genre, year, total_copies, available) VALUES (?,?,?,?,1,1)",
                (b["title"], b["author"], b.get("genre", "General"), b.get("year"))
            )
    conn.commit()
    logger.info("API books stored successfully.")


def save_books_as_json(books: list[dict], filepath: str = JSON_OUTPUT) -> None:
    """Save a list of book dicts to a JSON file."""
    logger.info("Saving %d books as JSON to %s", len(books), filepath)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(books, f, indent=2, ensure_ascii=False)
        logger.info("JSON output saved.")
    except OSError as exc:
        logger.error("JSON save failed: %s", exc)
        raise


# ══════════════════════════════════════════════
#  PART F – DEBUGGING  (intentional bugs + fixes documented)
# ══════════════════════════════════════════════
#
#  BUG 1 (FIXED): Off-by-one in due-date calculation
#    BUGGY  → due_date = loan_date + timedelta(days=0)  # due same day!
#    FIXED  → due_date = loan_date + timedelta(days=14)
#    Found by: print-debugging then logging
#
#  BUG 2 (FIXED): Wrong SQL column name in export
#    BUGGY  → "SELECT titl, author, available FROM books"   # typo: 'titl'
#    FIXED  → "SELECT title, author, available FROM books"
#    Found by: sqlite3.OperationalError caught in exception handler
#
#  BUG 3 (FIXED): Mutable default argument in fetch function
#    BUGGY  → def fetch_books_from_api(query, limit=[5]):  # list default – shared state bug
#    FIXED  → def fetch_books_from_api(query: str, limit: int = 5):
#    Found by: code review; verified with print debugging
#

def demonstrate_bugs() -> None:
    """Run three isolated demonstrations of intentional bugs that were fixed."""
    print("\n" + "═"*60)
    print("  PART F – DEBUGGING DEMONSTRATION")
    print("═"*60)

    # ── Bug 1 demonstration (fixed) ──
    loan_date = date(2026, 5, 1)
    # BUG version:  due_date_bug = loan_date + timedelta(days=0)
    due_date_fix = loan_date + timedelta(days=14)
    print(f"\n[Bug 1 FIXED] Due date: {due_date_fix}  (was same-day before fix)")

    # ── Bug 2 demonstration (fixed) ──
    try:
        conn_tmp = sqlite3.connect(":memory:")
        conn_tmp.execute("CREATE TABLE books (title TEXT, author TEXT, available INTEGER)")
        conn_tmp.execute("INSERT INTO books VALUES ('Test','Auth',1)")
        # BUG version: conn_tmp.execute("SELECT titl, author, available FROM books")
        result = conn_tmp.execute("SELECT title, author, available FROM books").fetchall()
        print(f"[Bug 2 FIXED] SQL query returned: {result[0]}")
    except sqlite3.OperationalError as e:
        print(f"[Bug 2] Would have raised: {e}")
    finally:
        conn_tmp.close()

    # ── Bug 3 demonstration (mutable default) ──
    def bad_default(items=[]):          # mutable default – bad practice
        items.append("x")
        return items
    r1, r2 = bad_default(), bad_default()
    print(f"[Bug 3] Mutable default creates shared state: {r1} is {r2} → {r1 is r2}")
    # Fixed version uses items=None and items = items or []


# ══════════════════════════════════════════════
#  PROFILING HELPER
# ══════════════════════════════════════════════

def profile_function(func, *args, **kwargs):
    """Run a function under cProfile and print the top-10 stats."""
    pr = cProfile.Profile()
    pr.enable()
    result = func(*args, **kwargs)
    pr.disable()
    stream = io.StringIO()
    ps = pstats.Stats(pr, stream=stream).sort_stats("cumulative")
    ps.print_stats(10)
    logger.info("Profiling results for %s:\n%s", func.__name__, stream.getvalue())
    return result


# ══════════════════════════════════════════════
#  SEED DATA
# ══════════════════════════════════════════════

def seed_data(conn: sqlite3.Connection) -> None:
    """Populate tables with initial sample data (idempotent)."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM members")
    if cur.fetchone()["c"] > 0:
        logger.info("Database already seeded, skipping.")
        return

    logger.info("Seeding sample data…")

    members = [
        ("Mahmood Al Maawali", "Mahmood@library.com"),
        ("Sultan AL Hamaili",     "Sultan@library.com"),
        ("Ibrahim Al Lawati",   "Ibrahim@library.com"),
    ]
    for name, email in members:
        add_member(conn, name, email)

    books = [
        ("Clean Code",             "Robert C. Martin", "Programming",  2008, 3),
        ("The Great Gatsby",       "F. Scott Fitzgerald","Fiction",    1925, 2),
        ("Thinking, Fast and Slow","Daniel Kahneman",   "Psychology",  2011, 2),
        ("Sapiens",                "Yuval Noah Harari", "History",     2011, 4),
        ("Python Crash Course",    "Eric Matthes",      "Programming", 2015, 2),
    ]
    for title, author, genre, year, copies in books:
        add_book(conn, title, author, genre, year, copies)

    # Issue one book
    issue_book(conn, member_id=1, book_id=1)
    logger.info("Seed complete.")


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

def main() -> None:
    logger.info("=" * 60)
    logger.info("Library Management System – Starting up")
    logger.info("=" * 60)

    # ── Part B/C – DB init & seed ─────────────
    conn = init_db()
    seed_data(conn)

    # ── Part C – Queries ──────────────────────
    print("\n📚  ALL BOOKS")
    print(get_all_books(conn).to_string(index=False))

    print("\n👥  ALL MEMBERS")
    print(get_all_members(conn).to_string(index=False))

    print("\n📖  ACTIVE LOANS")
    print(get_active_loans(conn).to_string(index=False))

    print("\n🔍  QUERY 1 – Available Programming books (AND operator)")
    print(search_available_books_by_genre(conn, "Programming").to_string(index=False))

    print("\n⚠️   QUERY 2 – Overdue / late returns (OR operator)")
    overdue = get_overdue_or_missing(conn)
    print(overdue.to_string(index=False) if not overdue.empty else "  No overdue loans 🎉")

    # ── Part D – CSV Export / Import ──────────
    export_books_to_csv(conn)
    df_imported = import_csv_to_dataframe()
    print(f"\n📂  CSV IMPORT – {len(df_imported)} records loaded")
    print(df_imported.to_string(index=False))

    # ── Part E – API ──────────────────────────
    print("\n🌐  FETCHING from Open Library API…")
    try:
        api_books = profile_function(fetch_books_from_api, "python programming", limit=5)
        store_api_books(conn, api_books)
        save_books_as_json(api_books)
        print(json.dumps(api_books, indent=2))
    except Exception as exc:
        logger.error("API section failed: %s", exc)
        print(f"  API unavailable: {exc}")

    # ── Part F – Debugging demo ───────────────
    demonstrate_bugs()

    # ── Wrap up ───────────────────────────────
    conn.close()
    logger.info("Application finished successfully.")
    print("\n✅  Done! Check logs/library.log for full log output.")


if __name__ == "__main__":
    main()
