import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.db")

SCHEMA = {
    "customers": {
        "columns": ["id INTEGER PRIMARY KEY", "name TEXT NOT NULL", "email TEXT UNIQUE", "city TEXT", "join_date TEXT"],
        "description": "Stores customer information",
    },
    "categories": {
        "columns": ["id INTEGER PRIMARY KEY", "name TEXT NOT NULL", "description TEXT"],
        "description": "Product categories",
    },
    "products": {
        "columns": ["id INTEGER PRIMARY KEY", "name TEXT NOT NULL", "price REAL NOT NULL", "category_id INTEGER REFERENCES categories(id)", "stock INTEGER DEFAULT 0"],
        "description": "Available products",
    },
    "orders": {
        "columns": ["id INTEGER PRIMARY KEY", "customer_id INTEGER REFERENCES customers(id)", "order_date TEXT NOT NULL", "status TEXT DEFAULT 'pending'"],
        "description": "Customer orders",
    },
    "order_items": {
        "columns": ["id INTEGER PRIMARY KEY", "order_id INTEGER REFERENCES orders(id)", "product_id INTEGER REFERENCES products(id)", "quantity INTEGER NOT NULL", "unit_price REAL NOT NULL"],
        "description": "Individual items within an order",
    },
    "employees": {
        "columns": ["id INTEGER PRIMARY KEY", "name TEXT NOT NULL", "role TEXT NOT NULL", "department TEXT", "salary REAL", "hire_date TEXT"],
        "description": "Company employees",
    },
}

SAMPLE_DATA = {
    "customers": [
        (1, "Alice Johnson", "alice@example.com", "New York", "2023-01-15"),
        (2, "Bob Smith", "bob@example.com", "Los Angeles", "2023-03-22"),
        (3, "Charlie Brown", "charlie@example.com", "Chicago", "2023-06-01"),
        (4, "Diana Prince", "diana@example.com", "New York", "2023-09-10"),
        (5, "Eve Davis", "eve@example.com", "Houston", "2024-01-05"),
    ],
    "categories": [
        (1, "Electronics", "Gadgets and devices"),
        (2, "Books", "Physical and digital books"),
        (3, "Clothing", "Apparel and accessories"),
        (4, "Home & Kitchen", "Household items"),
    ],
    "products": [
        (1, "Wireless Mouse", 29.99, 1, 150),
        (2, "Mechanical Keyboard", 89.99, 1, 75),
        (3, "Python Crash Course", 35.50, 2, 200),
        (4, "Clean Code", 42.00, 2, 120),
        (5, "Cotton T-Shirt", 19.99, 3, 300),
        (6, "Denim Jacket", 59.99, 3, 50),
        (7, "Coffee Maker", 79.99, 4, 60),
        (8, "Air Fryer", 119.99, 4, 40),
    ],
    "orders": [
        (1, 1, "2024-06-01", "delivered"),
        (2, 2, "2024-06-05", "delivered"),
        (3, 1, "2024-06-10", "shipped"),
        (4, 3, "2024-06-12", "pending"),
        (5, 4, "2024-06-15", "delivered"),
        (6, 5, "2024-06-20", "pending"),
    ],
    "order_items": [
        (1, 1, 1, 2, 29.99),
        (2, 1, 3, 1, 35.50),
        (3, 2, 2, 1, 89.99),
        (4, 2, 4, 2, 42.00),
        (5, 3, 5, 3, 19.99),
        (6, 3, 7, 1, 79.99),
        (7, 4, 8, 1, 119.99),
        (8, 5, 6, 2, 59.99),
        (9, 5, 3, 1, 35.50),
        (10, 6, 1, 1, 29.99),
    ],
    "employees": [
        (1, "Frank Castle", "Manager", "Sales", 75000, "2022-04-10"),
        (2, "Grace Hopper", "Developer", "Engineering", 95000, "2022-06-15"),
        (3, "Hank Pym", "Developer", "Engineering", 90000, "2023-01-20"),
        (4, "Ivy Chen", "Designer", "Marketing", 70000, "2023-05-01"),
        (5, "Jack Ryan", "Sales Rep", "Sales", 60000, "2024-02-10"),
    ],
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for table, info in SCHEMA.items():
        cols = ", ".join(info["columns"])
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(f"CREATE TABLE {table} ({cols})")

    for table, rows in SAMPLE_DATA.items():
        placeholders = ", ".join(["?"] * len(rows[0]))
        cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)

    conn.commit()
    conn.close()


def get_schema_text() -> str:
    lines = []
    for table, info in SCHEMA.items():
        col_defs = [c.split()[0] for c in info["columns"]]
        lines.append(f"Table: {table} — {info['description']}")
        lines.append(f"  Columns: {', '.join(col_defs)}")
    return "\n".join(lines)


def get_schema_for_prompt() -> str:
    lines = []
    for table, info in SCHEMA.items():
        lines.append(f"{table}({', '.join(c for c in info['columns'])})")
    return "\n".join(lines)
