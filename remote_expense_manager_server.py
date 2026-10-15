import json
import sqlite3
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent / "expenses.db"

mcp = FastMCP(name="Expense_Tracker_server")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
            """
        )

init_db()


@mcp.tool()
def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = "",
) -> str:
    """Add a new expense to the database.

    date: YYYY-MM-DD
    amount: expense amount
    category: top-level category such as Food or Transport
    subcategory: optional finer category
    note: optional free-text note
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO expenses (date, amount, category, subcategory, note) VALUES (?, ?, ?, ?, ?)",
            (date, amount, category, subcategory, note),
        )
    return (
        f"Expense added for {date}: {amount} in {category}"
        + (f" / {subcategory}" if subcategory else "")
        + (f" ({note})" if note else "")
    )

#--------------------------------------------------------
@mcp.tool()
def list_expenses(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 50000,

) -> dict:
    """List expenses, newest first, with optional filters.

    Dates are inclusive and use YYYY-MM-DD. Category and subcategory
    matches are case-insensitive. Returns the matching rows, how many
    matched, the total amount, and a breakdown by category.
    """
    limit = max(1, min(limit, 200))

    clauses: list[str] = []
    params: list[object] = []

    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            {where}
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        count, total = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses {where}",
            params,
        ).fetchone()
        by_category = conn.execute(
            f"""
            SELECT MIN(category) AS category, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
            FROM expenses
            {where}
            GROUP BY LOWER(category)
            ORDER BY total DESC
            """,
            params,
        ).fetchall()

    return {
        "count": count,
        "shown": len(rows),
        "total_amount": round(total, 2),
        "by_category": [
            {
                "category": row["category"],
                "count": row["count"],
                "total": round(row["total"], 2),
            }
            for row in by_category
        ],
        "expenses": [
            {
                "id": row["id"],
                "date": row["date"],
                "amount": row["amount"],
                "category": row["category"],
                "subcategory": row["subcategory"],
                "note": row["note"],
            }
            for row in rows
        ],
    } 

#--------------------------------------------------------
@mcp.tool()
def get_expense(id: int) -> dict:
    """Get an expense by ID.

    id: expense ID
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (id,)).fetchone()
        if row is None:
            return {"error": f"Expense {id} not found"}
        return {
            "id": row["id"],
            "date": row["date"],
            "amount": row["amount"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "note": row["note"],
        }
#--------------------------------------------------------

@mcp.tool()
def edit_expense(id: int, date: str, amount: float, category: str, subcategory: str = "", note: str = "") -> str:
    """Edit an expense by ID.

    id: expense ID
    date: YYYY-MM-DD
    amount: expense amount
    category: top-level category such as Food or Transport
    subcategory: optional finer category
    note: optional free-text note
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE expenses SET date = ?, amount = ?, category = ?, subcategory = ?, note = ? WHERE id = ?", (date, amount, category, subcategory, note, id))
    return f"Expense updated: {id} {date} {amount} {category} {subcategory} {note}"

#--------------------------------------------------------
@mcp.tool()
def delete_expense(id: int) -> str:
    """Delete an expense by ID.
    id: expense ID
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (id,))
    return f"Expense deleted: {id}"

#--------------------------------------------------------

@mcp.resource("info://server")
def server_info() -> str: 
    """Get information about the server."""

    info = {"name": "Expense Tracker Server", 
    "version": "1.0.0",
    "description": "A simple server for expense tracking and management",
    "tools" : ["add_expense", "list_expenses", "get_expense", "edit_expense", "delete_expense"],
    "author": "Omkar Vibute",
    "email": "vibhuteomkar64@gmail.com",
    "website": "https://example.com",
    "license": "MIT",
    "contact": "vibhuteomkar64@gmail.com"
    }
    return json.dumps(info, indent=4)


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> JSONResponse:
    """Browser landing page. MCP clients must use /mcp, not this URL."""
    return JSONResponse(
        {
            "status": "ok",
            "server": "Expense_Tracker_server",
            "mcp_url": "http://127.0.0.1:8000/mcp",
            "note": "Streamable HTTP clients connect to mcp_url.",
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """HTTP health check. The MCP endpoint is /mcp."""
    return JSONResponse(
        {
            "status": "ok",
            "server": "Expense_Tracker_server",
            "mcp_url": "http://127.0.0.1:8000/mcp",
        }
    )


if __name__ == "__main__":
    # Streamable HTTP. Clients POST to http://127.0.0.1:8000/mcp
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")

    