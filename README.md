# Natural Language to SQL Agent

A Streamlit application that converts natural language questions into SQLite SQL queries using LangGraph, LangChain, and OpenAI.

---

## Setup

### Prerequisites

- Python 3.9+
- A OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/nl-to-sql-agent.git
cd nl-to-sql-agent

# Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

No `.env` file is needed. Enter your OpenAI API key in the **Settings** panel in the sidebar when the app starts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                    │
│                                                                 │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  API Key      │  │  Chat Input      │  │  Schema Browser   │  │
│  │  (Settings)   │  │                  │  │  (Sidebar)        │  │
│  └──────┬───────┘  └────────┬─────────┘  └───────────────────┘  │
└─────────┼───────────────────┼───────────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SQLQueryAgent (agent.py)                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LangGraph StateGraph                        │   │
│  │                                                          │   │
│  │   ┌─────────────────┐         ┌──────────┐              │   │
│  │   │  generate_sql    │────────▶│   END    │              │   │
│  │   │  (LLM Node)     │         └──────────┘              │   │
│  │   └─────────────────┘                                   │   │
│  │         │                                               │   │
│  │         ▼                                               │   │
│  │   ChatOpenAI (GPT-4o-mini)                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Database Layer (database.py)                  │
│                                                                 │
│   SQLite (data.db)                                              │
│   ┌────────────┬────────────┬──────────┬─────────┬───────────┐  │
│   │ customers  │ categories │ products │ orders  │ employees │  │
│   └────────────┴────────────┴──────────┴─────────┴───────────┘  │
│                        order_items                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## LangGraph / LangChain Workflow

### State Definition

The agent uses a `TypedDict`-based state that flows through the graph:

```python
class AgentState(TypedDict):
    messages: Sequence[BaseMessage]   # conversation history
    user_query: str                   # the user's natural language question
    sql_query: str                    # generated SQL (output)
    response: str                     # reserved for future use
    context: dict                     # carries over context from previous queries
    error: str                        # non-empty if the question cannot be answered
```

### Graph Structure

The workflow is a single-node `StateGraph`:

```
ENTRY ──▶ generate_sql ──▶ END
```

1. **`generate_sql` node** (`src/agent.py:35`):
   - Pulls the database schema via `get_schema_for_prompt()`
   - Constructs a system prompt that includes the full schema and strict rules
   - Creates a `ChatOpenAI` instance (GPT-4o-mini, temperature=0)
   - Invokes the LLM with `[SystemMessage, HumanMessage]`
   - Strips markdown code fences from the response
   - If the LLM returns `CANNOT_ANSWER` (question can't be mapped to the schema), sets `error` in state
   - Returns updated state with the SQL query or error

2. **`END`**: Terminal node — the graph completes and returns the final state.

### Agent Class

`SQLQueryAgent` wraps the graph and manages:

- **Lazy initialization**: The LLM and graph are only created on the first query (when the API key is available)
- **Conversation history**: Each query and its SQL result are appended to `messages`
- **Context carryover**: The last generated SQL is stored in `context["last_query"]` for potential follow-up questions
- **Error propagation**: If the graph sets an error, `query()` raises a `ValueError` with a user-friendly message

### Request Flow

```
User types question
        │
        ▼
  API key validated? ─── No ──▶ Show error, stop
        │ Yes
        ▼
  SQLQueryAgent.query(user_input, api_key)
        │
        ▼
  _ensure_graph() sets OPENAI_API_KEY env var
        │
        ▼
  Initial AgentState constructed with user_query
        │
        ▼
  graph.invoke(state)
        │
        ▼
  generate_sql():
    1. Build system prompt with schema
    2. Call Gemini LLM
    3. Parse response
        │
        ├── LLM returns SQL ──▶ state.sql_query = "SELECT ..."
        │
        └── LLM returns CANNOT_ANSWER ──▶ state.error = "Your request..."
        │
        ▼
  SQLQueryAgent checks for error
        │
        ├── error present ──▶ raise ValueError (shown in UI)
        │
        └── no error ──▶ Return SQL query, display in UI
```

---

## Database Schema

An SQLite database (`data.db`) is auto-created on app start with 6 tables and sample data:

| Table          | Description                          | Key Columns                                         |
|----------------|--------------------------------------|-----------------------------------------------------|
| `customers`    | Customer information                 | id, name, email, city, join_date                    |
| `categories`   | Product categories                   | id, name, description                               |
| `products`     | Available products                   | id, name, price, category_id, stock                 |
| `orders`       | Customer orders                      | id, customer_id, order_date, status                 |
| `order_items`  | Line items within an order           | id, order_id, product_id, quantity, unit_price      |
| `employees`    | Company employees                    | id, name, role, department, salary, hire_date       |

**Relationships:**
- `products.category_id` → `categories.id`
- `orders.customer_id` → `customers.id`
- `order_items.order_id` → `orders.id`
- `order_items.product_id` → `products.id`

---

## Project Structure

```
nl-to-sql-agent/
├── app.py                 # Streamlit UI — entry point
├── requirements.txt       # Python dependencies
├── .env.example           # (Legacy) API key template — no longer required
├── README.md
└── src/
    ├── __init__.py
    ├── agent.py           # LangGraph agent, LLM invocation, state management
    └── database.py        # Schema definition, SQLite init, sample data
```

## Example Questions

- "Show me all customers from New York"
- "What are the top 3 most expensive products?"
- "List all orders placed by Alice Johnson"
- "What is the total revenue by category?"
- "How many employees work in Engineering?"
- "Show me all products with stock less than 100"

If you ask something the schema cannot answer (e.g. "What's the weather today?"), the agent will return an error message instead of generating invalid SQL.
