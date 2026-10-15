import os
from pathlib import Path

import aiosqlite

from fastmcp import FastMCP

DB_PATH = Path(os.environ.get("EXPENSE_DB_PATH", Path(__file__).resolve().parent / "expenses.db"))

mcp = FastMCP(name="Expense_Tracker_server")


_ready = False


async def init_db() -> None:
    global _ready
    if _ready:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
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
        await db.commit()
    _ready = True


@mcp.tool()
async def add_expense(
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
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO expenses (date, amount, category, subcategory, note) VALUES (?, ?, ?, ?, ?)",
            (date, amount, category, subcategory, note),
        )
        await db.commit()
    return (
        f"Expense added for {date}: {amount} in {category}"
        + (f" / {subcategory}" if subcategory else "")
        + (f" ({note})" if note else "")
    )

#--------------------------------------------------------
@mcp.tool()
async def list_expenses(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 50,
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

    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            f"""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            {where}
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            (*params, limit),
        )).fetchall()
        count, total = await (await db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses {where}",
            params,
        )).fetchone()
        by_category = await (await db.execute(
            f"""
            SELECT MIN(category) AS category, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total
            FROM expenses
            {where}
            GROUP BY LOWER(category)
            ORDER BY total DESC
            """,
            params,
        )).fetchall()

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
async def get_expense(id: int) -> dict:
    """Get an expense by ID.

    id: expense ID
    """
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM expenses WHERE id = ?", (id,))).fetchone()
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
async def edit_expense(id: int, date: str, amount: float, category: str, subcategory: str = "", note: str = "") -> str:
    """Edit an expense by ID.

    id: expense ID
    date: YYYY-MM-DD
    amount: expense amount
    category: top-level category such as Food or Transport
    subcategory: optional finer category
    note: optional free-text note
    """
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE expenses SET date = ?, amount = ?, category = ?, subcategory = ?, note = ? WHERE id = ?", (date, amount, category, subcategory, note, id))
        await db.commit()
    return f"Expense updated: {id} {date} {amount} {category} {subcategory} {note}"

#--------------------------------------------------------
@mcp.tool()
async def delete_expense(id: int) -> str:
    """Delete an expense by ID.
    id: expense ID
    """
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM expenses WHERE id = ?", (id,))
        await db.commit()
    return f"Expense deleted: {id}"

#--------------------------------------------------------

if __name__ == "__main__":
    mcp.run()



#uv run fastmcp install claude-desktop expense_manager.py --config-path "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude 
# uv run fastmcp install claude-desktop main.py --config-path "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude" 

