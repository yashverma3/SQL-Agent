from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# MUST be the very first Streamlit command executed!
st.set_page_config(page_title="NL to SQL Agent", page_icon="🔍", layout="wide")

from src.agent import SQLQueryAgent
from src.database import init_db, get_schema_text, SCHEMA

# Cache DB initialization
@st.cache_resource
def setup_database():
    
    init_db()

setup_database()

st.title("🔍 Natural Language to SQL Agent")
st.markdown("Ask a question about the database, get the SQL query.")


def describe_provider_error(provider: str, error: Exception) -> str:
    """Return a safe, actionable message without including the submitted API key."""
    message = str(error).lower()

    if "401" in message or "invalid_api_key" in message or "api key not valid" in message:
        return f"The {provider} API key was rejected. Check that you selected the matching provider and pasted a current key."
    if "429" in message or "quota" in message or "resource has been exhausted" in message:
        return f"{provider} free-tier limit reached. Wait for the quota to reset or check the provider's usage limits."
    if "403" in message or "permission_denied" in message or "permission denied" in message:
        return f"{provider} denied this request. Make sure the API is enabled for the project that created this key."
    if "404" in message or "not found" in message or "not supported for generatecontent" in message:
        return f"The configured {provider} model is unavailable for this key or region. Create a new key in Google AI Studio and try again."
    if "location is not supported" in message or "unsupported country" in message:
        return f"{provider} is not currently available for this key's location or project."
    return f"{provider} returned an unexpected error. Please retry once; the local server log now records a safe diagnostic."


if "agent" not in st.session_state:
    st.session_state.agent = SQLQueryAgent()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "api_key" not in st.session_state or not isinstance(st.session_state.api_key, dict):
    st.session_state.api_key = {"OpenAI": "", "Gemini": ""}

if "provider" not in st.session_state:
    st.session_state.provider = "Gemini"

with st.sidebar:
    with st.expander("⚙️ Settings", expanded=not bool(st.session_state.api_key[st.session_state.provider])):
        provider = st.selectbox(
            "AI provider",
            options=["Gemini", "OpenAI"],
            key="provider",
            help="Gemini 3.5 Flash has a free tier with usage limits. OpenAI requires API billing.",
        )
        key_input = st.text_input(
            f"{provider} API Key",
            value=st.session_state.api_key[provider],
            type="password",
            placeholder=f"Enter your {provider} API key",
            help="The key stays only in this browser session and is never saved to disk.",
        )
        if key_input:
            st.session_state.api_key[provider] = key_input

        if provider == "Gemini":
            st.caption("Uses Gemini 3.5 Flash on Google's available free tier.")

    st.divider()
    st.subheader("📋 Database Schema")
    for table, info in SCHEMA.items():
        with st.expander(f"📦 {table}"):
            st.caption(info["description"])
            cols = [c.split()[0] for c in info["columns"]]
            st.table({"Column": cols})

    st.divider()
    st.subheader("💡 Example Questions")
    examples = [
        "Show me all customers from New York",
        "What are the top 3 most expensive products?",
        "List all orders placed by Alice Johnson",
        "What is the total revenue by category?",
        "How many employees work in Engineering?",
        "Show me all products with stock less than 100",
    ]
    for example in examples:
        if st.button(example, key=example):
            st.session_state.user_input = example

    st.divider()
    if st.button("🗑️ Clear History"):
        st.session_state.agent.reset()
        st.session_state.chat_history = []
        st.rerun()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            if msg.get("kind") == "error":
                st.error(msg["content"])
            else:
                st.code(msg["content"], language="sql")
        else:
            st.markdown(msg["content"])

chat_input_value = st.chat_input("Ask a question about the database...")

if "user_input" in st.session_state and st.session_state.user_input:
    user_input = st.session_state.user_input
    st.session_state.user_input = None
else:
    user_input = chat_input_value

if user_input:
    provider = st.session_state.provider
    api_key = st.session_state.api_key[provider]
    if not api_key:
        st.error(f"Please enter your {provider} API key in the sidebar Settings.")
        st.stop()

    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Generating SQL..."):
            try:
                sql = st.session_state.agent.query(user_input, api_key, provider)
                st.code(sql, language="sql")
                st.session_state.chat_history.append({"role": "assistant", "content": sql})
            except ValueError as e:
                st.error(str(e))
                st.session_state.chat_history.append({"role": "assistant", "content": str(e), "kind": "error"})
            except Exception as e:
                # Keep the key out of the UI while retaining a local diagnostic for support.
                print(f"[{provider}] {type(e).__name__}: {e}")
                user_friendly_err = describe_provider_error(provider, e)
                st.error(user_friendly_err)
                st.session_state.chat_history.append({"role": "assistant", "content": user_friendly_err, "kind": "error"})