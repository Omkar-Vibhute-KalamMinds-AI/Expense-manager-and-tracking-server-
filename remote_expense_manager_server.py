import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
import aiosqlite
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fastmcp import FastMCP

def _db_path() -> Path:
    if os.environ.get("EXPENSE_DB_PATH"):
        return Path(os.environ["EXPENSE_DB_PATH"])
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "ExpenseTracker" / "expenses.db"
    return Path(__file__).resolve().parent / "expenses.db"


DB_PATH = _db_path()


@asynccontextmanager
async def open_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=OFF")
        yield db

mcp = FastMCP(name="Expense_Tracker_server")


_ready = False


async def init_db() -> None:
    global _ready
    if _ready:
        return
    async with open_db() as db:
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
    async with open_db() as db:
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
    limit: int | None = None,

) -> dict:
    """List expenses, newest first, with optional filters.

    Dates are inclusive and use YYYY-MM-DD. Category and subcategory
    matches are case-insensitive. Returns the matching rows, how many
    matched, the total amount, and a breakdown by category.
    """
    limit = max(1, min(limit or 50000, 200))

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
    async with open_db() as db:
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
    async with open_db() as db:
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
    async with open_db() as db:
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
    async with open_db() as db:
        await db.execute("DELETE FROM expenses WHERE id = ?", (id,))
        await db.commit()
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


@mcp.custom_route("/json/version", methods=["GET"])
async def browser_probe(request: Request) -> JSONResponse:
    """Browsers ask for a Chrome debug port. This server is not one."""
    return JSONResponse({"status": "ok", "note": "This is an MCP server, not a browser debug port."})


class QuietBrowserGet:
    """Answer a browser GET /mcp. Real clients send a session id or POST."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "GET" and scope.get("path") == "/mcp":
            names = {key.lower() for key, _ in scope.get("headers", [])}
            if b"mcp-session-id" not in names:
                body = json.dumps(
                    {
                        "status": "ok",
                        "server": "Expense_Tracker_server",
                        "mcp_url": "http://127.0.0.1:8000/mcp",
                        "note": "Streamable HTTP is ready. An MCP client must POST initialize to this URL.",
                    }
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(body)).encode()],
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


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
    try:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=8000,
            path="/mcp",
            middleware=[Middleware(QuietBrowserGet)],
        )
    except KeyboardInterrupt:
        pass 