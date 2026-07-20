import re
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

from src.database import get_schema_for_prompt


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], "The conversation history"]
    user_query: str
    sql_query: str
    statement_type: str
    response: str
    context: dict
    error: str


SYSTEM_PROMPT = """You are a SQL expert. Convert natural language questions or instructions into valid SQLite SQL statements.

DATABASE SCHEMA:
{schema}

STRICT RULES:
1. You may generate SELECT, INSERT, UPDATE, or DELETE statements — including joins, subqueries, aggregations, CASE expressions, GROUP BY/HAVING, and multi-table conditions where the question calls for them.
2. Never generate DDL statements (CREATE, DROP, ALTER, TRUNCATE) or administrative commands (PRAGMA, ATTACH, DETACH, VACUUM, REINDEX), even if asked directly.
3. Use proper SQLite syntax.
4. Return ONLY the SQL statement, no explanations or markdown, and no trailing semicolon.
5. You may ONLY use tables and columns listed in the schema above. Do not hallucinate table or column names that do not exist in the schema.
6. Generate exactly ONE SQL statement per response — never chain multiple statements together.
7. For UPDATE and DELETE statements, include a WHERE clause that reflects the specific condition described in the request. Only write an UPDATE/DELETE with no WHERE clause if the user has explicitly and unambiguously asked to affect every row in the table.
8. If the request cannot be fulfilled with the given schema, or is ambiguous about which rows should be affected by an UPDATE/DELETE, respond with exactly: CANNOT_ANSWER
"""

# Statement types this agent is allowed to produce. Defense-in-depth check
# performed in code, independent of what the prompt asks the model to do —
# an LLM's output is never fully trusted as the only safety boundary.
ALLOWED_STATEMENT_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE"}

FORBIDDEN_KEYWORDS_PATTERN = re.compile(
    r"\b(create|drop|alter|truncate|pragma|attach|detach|vacuum|reindex|replace\s+into)\b",
    re.IGNORECASE,
)


def _get_statement_type(sql: str) -> str:
    match = re.match(r"\s*(select|insert|update|delete)\b", sql, re.IGNORECASE)
    return match.group(1).upper() if match else "UNKNOWN"


def generate_sql(state: AgentState, llm) -> AgentState:
    schema_text = get_schema_for_prompt()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(schema=schema_text)),
        *state["messages"],
    ]
    response = llm.invoke(messages)
    sql_raw = response.content.strip()

    if sql_raw == "CANNOT_ANSWER":
        return {**state, "sql_query": "", "statement_type": "", "error": "Your request cannot be fulfilled with the available database tables and columns, or is ambiguous about which rows to affect."}

    sql_query = re.sub(r"```sql\s*", "", sql_raw)
    sql_query = re.sub(r"```\s*$", "", sql_query)
    sql_query = sql_query.strip().rstrip(";").strip()

    # --- Defense-in-depth validation (independent of the prompt) ---
    if ";" in sql_query:
        return {**state, "sql_query": "", "statement_type": "", "error": "Only a single SQL statement is supported per request."}

    if FORBIDDEN_KEYWORDS_PATTERN.search(sql_query):
        return {**state, "sql_query": "", "statement_type": "", "error": "Schema-altering or administrative statements (CREATE/DROP/ALTER/PRAGMA/etc.) are not supported."}

    statement_type = _get_statement_type(sql_query)
    if statement_type not in ALLOWED_STATEMENT_TYPES:
        return {**state, "sql_query": "", "statement_type": "", "error": "Only SELECT, INSERT, UPDATE, and DELETE statements are supported."}

    return {**state, "sql_query": sql_query, "statement_type": statement_type, "error": ""}


def create_agent_graph(llm) -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("generate_sql", lambda state: generate_sql(state, llm))
    workflow.set_entry_point("generate_sql")
    workflow.add_edge("generate_sql", END)
    return workflow.compile()


class SQLQueryAgent:
    def __init__(self):
        self.conversation_history: list[BaseMessage] = []
        self.context: dict = {}
        self.graph = None
        self._active_provider = None
        self._active_api_key = None

    def _ensure_graph(self, api_key: str, provider: str):
        if self.graph is not None and (provider, api_key) == (self._active_provider, self._active_api_key):
            return

        if provider == "Gemini":
            llm = ChatGoogleGenerativeAI(
                model="gemini-3.5-flash",
                temperature=0,
                google_api_key=api_key,
                max_retries=1,      # avoid silent multi-minute retry loops on rate limits
                timeout=30,
            )
        else:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=api_key,
                max_retries=1,
                timeout=30,
            )

        self.graph = create_agent_graph(llm)
        self._active_provider = provider
        self._active_api_key = api_key

    def query(self, user_input: str, api_key: str, provider: str = "OpenAI") -> str:
        self._ensure_graph(api_key, provider)
        self.conversation_history.append(HumanMessage(content=user_input))

        # Only send the most recent turns to the model. Sending the full,
        # ever-growing history on every call makes each request slower (and
        # pricier) the longer the conversation goes on, since the whole
        # schema + all prior Q/A pairs get re-sent each time.
        max_turns = 6  # ~3 user/assistant exchanges of context
        recent_messages = self.conversation_history[-max_turns:]

        initial_state: AgentState = {
            "messages": recent_messages,
            "user_query": user_input,
            "sql_query": "",
            "response": "",
            "context": self.context.copy(),
            "error": "",
        }

        result = self.graph.invoke(initial_state)

        if result.get("error"):
            raise ValueError(result["error"])

        self.conversation_history.append(AIMessage(content=result["sql_query"]))
        self.context["last_query"] = result["sql_query"]
        self.context["last_statement_type"] = result.get("statement_type", "")

        return result["sql_query"]

    def reset(self):
        self.conversation_history = []
        self.context = {}
