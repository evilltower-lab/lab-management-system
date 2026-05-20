# Debugging Report – Library Management System

**Module:** Advanced Programming DTSC2207  
**Date:** May 2026

---

## Overview

As part of Part F of the project requirements, three intentional bugs were injected
into the codebase, then detected, fixed, and documented below.

---

## Bug 1 – Off-by-One in Loan Due-Date Calculation

### Location
`library_app.py` → `issue_book()` function

### Injected Bug (Buggy Code)
```python
# BUGGY – due_date same as loan_date
loan_date = date.today()
due_date  = loan_date + timedelta(days=0)   # <-- BUG: should be 14
```

### How It Was Detected
Print-debugging was used first:
```python
print(f"DEBUG loan_date={loan_date}  due_date={due_date}")
# Output: DEBUG loan_date=2026-05-01  due_date=2026-05-01   ← obviously wrong
```
Then replaced with:
```python
logger.debug("loan_date=%s due_date=%s", loan_date, due_date)
```

### Fix Applied
```python
due_date = loan_date + timedelta(days=14)   # FIXED
```

### Impact
All loans would immediately appear overdue, causing every query to incorrectly
flag borrowers. The `get_overdue_or_missing()` function returned every active loan.

---

## Bug 2 – Typo in SQL SELECT Statement

### Location
`library_app.py` → `export_books_to_csv()` function

### Injected Bug (Buggy Code)
```python
# BUGGY – column name typo
cur.execute("SELECT titl, author, available FROM books")
#                   ^^^^ should be 'title'
```

### How It Was Detected
The `sqlite3.OperationalError` exception was raised and caught:
```
sqlite3.OperationalError: no such column: titl
```
The `try/except` block in `export_books_to_csv()` caught this and logged it:
```
ERROR | library_app | CSV export failed: no such column: titl
```

### Fix Applied
```python
cur.execute("SELECT title, author, available FROM books")  # FIXED
```

### Impact
The CSV export file would not be created at all, breaking Part D of the project.

---

## Bug 3 – Mutable Default Argument

### Location
`library_app.py` → `fetch_books_from_api()` function

### Injected Bug (Buggy Code)
```python
# BUGGY – mutable list as default argument
def fetch_books_from_api(query, limit=[5]):
    # Python evaluates defaults once at function definition time.
    # Every call shares the same list object.
    limit.append(10)   # modifies the shared default on every call!
    ...
```

### How It Was Detected
Print debugging:
```python
print(f"DEBUG limit={limit}")
# Call 1: DEBUG limit=[5, 10]
# Call 2: DEBUG limit=[5, 10, 10]    ← grows on every call!
```

### Fix Applied
```python
# FIXED – use an immutable default (int)
def fetch_books_from_api(query: str, limit: int = 5) -> list[dict]:
    ...
```

### Impact
Repeated calls would pass an ever-growing list to the API, causing unexpected
request behaviour and potential API errors.

---

## Summary Table

| Bug # | Type | Function | Detection Method | Severity |
|-------|------|----------|-----------------|----------|
| 1 | Logic error (off-by-one) | `issue_book()` | Print debug → logging | High |
| 2 | SQL typo | `export_books_to_csv()` | Exception handler + logging | High |
| 3 | Mutable default argument | `fetch_books_from_api()` | Print debug + code review | Medium |

---

## Logging Replacement

All `print()` debugging statements were replaced with proper logging calls:

| Before | After |
|--------|-------|
| `print(f"DEBUG loan_date={loan_date}")` | `logger.debug("loan_date=%s", loan_date)` |
| `print(f"ERROR: {e}")` | `logger.error("Export failed: %s", e)` |
| `print("Done.")` | `logger.info("Operation completed.")` |
