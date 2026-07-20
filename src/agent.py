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
    response: str
    context: dict
    error: str


SYSTEM_PROMPT = """You are a SQL expert. Convert natural language questions into valid SQLite SQL queries.

DATABASE SCHEMA:
{schema}

STRICT RULES:
1. Only generate SELECT queries
2. Use proper SQLite syntax
3. Return ONLY the SQL query, no explanations or markdown
4. You may ONLY use tables and columns listed in the schema above
5. If the question cannot be answered with the given schema, respond with exactly: CANNOT_ANSWER
6. Do not hallucinate table or column names that do not exist in the schema
"""


def generate_sql(state: AgentState, llm) -> AgentState:
    schema_text = get_schema_for_prompt()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(schema=schema_text)),
        *state["messages"],
    ]
    response = llm.invoke(messages)
    sql_raw = response.content.strip()

    if sql_raw == "CANNOT_ANSWER":
        return {**state, "sql_query": "", "error": "Your request cannot be fulfilled with the available database tables and columns."}

    sql_query = re.sub(r"```sql\s*", "", sql_raw)
    sql_query = re.sub(r"```\s*$", "", sql_query)
    return {**state, "sql_query": sql_query.strip(), "error": ""}


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
            )
        else:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)

        self.graph = create_agent_graph(llm)
        self._active_provider = provider
        self._active_api_key = api_key

    def query(self, user_input: str, api_key: str, provider: str = "OpenAI") -> str:
        self._ensure_graph(api_key, provider)
        self.conversation_history.append(HumanMessage(content=user_input))

        initial_state: AgentState = {
            "messages": self.conversation_history,
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

        return result["sql_query"]

    def reset(self):
        self.conversation_history = []
        self.context = {}
