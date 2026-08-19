import streamlit as st
import os
import time
import json
import base64
import hmac
import hashlib
import numpy as np
import faiss
import google.auth
from google.cloud import bigquery
from sentence_transformers import SentenceTransformer
from streamlit_cookies_controller import CookieController

try:
    from google import genai
    from google.genai import types as genai_types
except ModuleNotFoundError:
    st.error("Missing package: google-genai. Run: pip install --upgrade google-genai")
    st.stop()

# =========================================================
# 1. PAGE CONFIG & UI STYLING
# =========================================================
st.set_page_config(page_title="NMHF SDOH Assistant", layout="centered")

_HIDE_STREAMLIT_CHROME = """
<style>
#MainMenu {visibility: hidden !important;}
footer {visibility: hidden !important;}
[data-testid="stDecoration"] {display: none !important;}
[data-testid="stStatusWidget"] {display: none !important;}
header[data-testid="stHeader"] {background: transparent !important;}
</style>
"""
st.markdown(_HIDE_STREAMLIT_CHROME, unsafe_allow_html=True)

# =========================================================
# 2. SECRETS, AUTHENTICATION, & GCP SETUP
# =========================================================
credentials, project = google.auth.default()

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or st.secrets.get("GOOGLE_CLOUD_PROJECT", "nmhf-477600")
GCP_LOCATION = os.getenv("GCP_REGION") or st.secrets.get("GCP_REGION", "us-east1")
# The BigQuery dataset that holds the actual numerical/statistical tables
# (as opposed to `nmhf_info`, which holds definitions/metadata).
NMHF_DATA_DATASET = os.getenv("NMHF_DATA_DATASET") or st.secrets.get("NMHF_DATA_DATASET", "NMHF")

genai_client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
bq_client = bigquery.Client(credentials=credentials, project=GCP_PROJECT)

# App Login Setup
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or st.secrets.get("ADMIN_PASSWORD", "nmhf2026")
_SESSION_SECRET = hashlib.sha256(("nmhf:" + (ADMIN_PASSWORD or "")).encode()).hexdigest().encode()
_SESSION_COOKIE_NAME = "nmhf_session_v1"
cookies = CookieController(key="cookies")

st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("chat_history", [])
st.session_state.setdefault("legacy_term_hits", 0)

def _login():
    st.session_state.authenticated = True
    payload = {"auth": True, "exp": int(time.time()) + 3600}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = base64.urlsafe_b64encode(hmac.new(_SESSION_SECRET, raw.encode(), hashlib.sha256).digest()).decode()
    cookies.set(_SESSION_COOKIE_NAME, f"{raw}.{sig}", max_age=3600)

if not st.session_state.authenticated:
    st.title("NMHF Data Assistant")
    code = st.text_input("Enter access code", type="password")
    if code:
        if code.strip() == ADMIN_PASSWORD:
            _login()
            st.rerun()
        else:
            st.error("Incorrect access code")
    st.stop()

# =========================================================
# 3. ACRONYM GLOSSARY
# =========================================================
# In sync with the ACRONYM_MAP in build_faiss_index.py. This copy
# is used to (a) hard-inject a glossary straight into the system prompt so
# the model always has it, with no retrieval step required, and (b) expand
# acronyms in the user's raw query before it's embedded for FAISS search,
# so retrieval quality doesn't depend on the model choosing to search for
# the acronym itself.
ACRONYM_MAP = {
    "ADI":  "Area Deprivation Index",
    "SVI":  "Social Vulnerability Index",
    "NDI":  "Neighborhood Deprivation Index",
    "SDOH": "Social Determinants of Health",
    "NMHF": "Non-Medical Health Factors",
    "AQI":  "Air Quality Index",
    "ACS":  "American Community Survey",
    "COI":  "Child Opportunity Index",
    "AHRQ": "Agency for Healthcare Research and Quality",
    "FBI":  "Federal Bureau of Investigation",
}

def _expand_acronyms(text: str) -> str:
    """Append full expansions for any recognized acronym found in the text,
    so the embedding model sees both the short and long form."""
    upper_text = text.upper()
    expansions = [
        f"{acr} ({full})"
        for acr, full in ACRONYM_MAP.items()
        if acr in upper_text
    ]
    if _uses_legacy_terminology(text):
        expansions.append("NMHF (Non-Medical Health Factors — same concept as SDOH / social determinants)")
    if expansions:
        return f"{text} [{'; '.join(expansions)}]"
    return text

_GLOSSARY_BLOCK = "\n".join(f"- {acr}: {full}" for acr, full in ACRONYM_MAP.items())

# ---------------------------------------------------------------------------
# Legacy terminology handling: SDOH / "social determinants (of health)" are
# older terms for what's now called NMHF. Some users will still use them —
# we never correct or flag that, we just treat the terms as fully
# interchangeable for search/routing, and occasionally (not every time)
# let the model mention the newer NMHF terminology in passing.
# ---------------------------------------------------------------------------
_LEGACY_TERMINOLOGY_PHRASES = ["sdoh", "social determinants of health", "social determinants"]

def _uses_legacy_terminology(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _LEGACY_TERMINOLOGY_PHRASES)

# =========================================================
# 4. FAISS INDEX (loaded once per server process)
# =========================================================
FAISS_INDEX_PATH    = os.getenv("FAISS_INDEX_PATH", "nmhf_faiss.index")
FAISS_METADATA_PATH = os.getenv("FAISS_METADATA_PATH", "nmhf_metadata.json")
EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"

@st.cache_resource(show_spinner="Loading knowledge base...")
def load_faiss_resources():
    """Loads the embedding model, FAISS index, and metadata mapping once
    and caches them for the life of the server process."""
    if not (os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_METADATA_PATH)):
        return None, None, None
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    return model, index, metadata

_embedding_model, _faiss_index, _faiss_metadata = load_faiss_resources()

# =========================================================
# 5. THE "DUAL-BRAIN" TOOLS
# =========================================================
def search_nmhf_documents(search_query: str) -> str:
    """
    Use this tool to find definitions, concepts, methodologies, and metadata
    about NMHF/SDOH data sources, including expanding acronyms like ADI,
    SVI, and NDI.
    """
    if _embedding_model is None or _faiss_index is None:
        return (
            "The local knowledge base index has not been built yet. "
            "Run build_faiss_index.py and deploy nmhf_faiss.index / "
            "nmhf_metadata.json alongside this app."
        )

    query_text = _expand_acronyms(search_query)
    query_embedding = _embedding_model.encode([query_text], convert_to_numpy=True)
    faiss.normalize_L2(query_embedding)

    top_k = 5
    scores, indices = _faiss_index.search(query_embedding, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_faiss_metadata):
            continue
        chunk = _faiss_metadata[idx]
        results.append(f"[{chunk.get('type', 'info')}] {chunk.get('text', '')}")

    if not results:
        return "No specific definition found. Please check the core documentation."

    return "\n".join(results)


def list_tables_for_category(category: str) -> str:
    """
    Use this tool BEFORE querying any NMHF statistical data table, whenever
    the user's request doesn't already specify an exact table (e.g. they
    said "ADI data" or "NDI" without a year or geography level, or "SVI"
    without specifying county vs. tract level).

    Pass a short category name (e.g. "ADI", "SVI", "NDI", "AQI"). This
    looks up every table in the NMHF dataset whose name starts with that
    category and returns the list of exact table name variants available,
    so you can ask the user to pick one before running query_nmhf_data.
    Works generically for any table category, not just ADI/SVI.
    """
    try:
        category_clean = category.strip().upper()
        query = f"""
            SELECT table_name
            FROM `{GCP_PROJECT}.{NMHF_DATA_DATASET}.INFORMATION_SCHEMA.TABLES`
            WHERE UPPER(table_name) LIKE @prefix
            ORDER BY table_name
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("prefix", "STRING", f"{category_clean}%")
            ]
        )
        rows = bq_client.query(query, job_config=job_config).result()
        table_names = [row["table_name"] for row in rows]

        if not table_names:
            return (
                f"No tables found in `{NMHF_DATA_DATASET}` starting with '{category_clean}'. "
                "Double-check the category name, or it may only exist in the nmhf_info "
                "definitions dataset rather than as a data table."
            )
        if len(table_names) == 1:
            return f"Exactly one matching table: `{table_names[0]}`. You can query it directly."

        formatted = ", ".join(f"`{t}`" for t in table_names)
        return f"Found {len(table_names)} matching tables for '{category_clean}': {formatted}. Ask the user which one they want."
    except Exception as e:
        return f"Could not list tables for category '{category}'. Error: {e}"


def query_nmhf_data(sql_query: str) -> str:
    """
    Use this tool to execute BigQuery SQL queries and fetch actual numerical
    data from the NMHF database. You must provide a valid BigQuery SQL
    string. Only call this once you know the exact table name — use
    list_tables_for_category first if you're not sure which table variant
    the user wants.
    """
    try:
        query_job = bq_client.query(sql_query)
        results_df = query_job.to_dataframe()
        if len(results_df) > 50:
            return f"Query successful, but returned {len(results_df)} rows. Here are the top 50: " + results_df.head(50).to_json(orient='records')
        return results_df.to_json(orient='records')
    except Exception as e:
        return f"SQL Query failed. Please correct your SQL and try again. Error: {e}"

# =========================================================
# 6. THE PERSONA (System Prompt)
# =========================================================
SYSTEM_PROMPT = f"""
You are an expert data assistant specializing in Social Determinants of Health (SDOH) and Non-Medical Health Factors (NMHF).

You have three tools:
- search_nmhf_documents: for definitions, concepts, and metadata (uses a local knowledge base).
- list_tables_for_category: for discovering which exact statistical tables exist for a topic.
- query_nmhf_data: for pulling actual numerical data via BigQuery SQL.

ACRONYM GLOSSARY (use this immediately, no need to search for these):
{_GLOSSARY_BLOCK}

TERMINOLOGY:
NMHF (Non-Medical Health Factors) and SDOH (Social Determinants of Health) / "social
determinants" refer to the exact same concept. Treat them as fully interchangeable when
understanding intent, searching, and routing queries. NEVER correct a user or point out that
they used the "wrong" or "older" term — many people still say SDOH or social determinants,
and that's completely fine. NMHF is simply the newer name Georgetown now uses for the same
thing. Each user message below may include a note telling you whether this is an appropriate
moment to casually mention that NMHF and SDOH are the same concept — only do so when that note
says it's appropriate, and even then keep it to one short, warm, in-passing sentence, never a
correction and never a lecture.

DATABASE STRUCTURE (Project: {GCP_PROJECT}):
There are two datasets: `nmhf_info` (for definitions/metadata) and `{NMHF_DATA_DATASET}` (for actual numerical statistics).

DATASET 1: `nmhf_info` (definitions, descriptions, schemas)
- General NMHF Info: `{GCP_PROJECT}.nmhf_info.all_info`
- SVI Descriptions/Schemas: `{GCP_PROJECT}.nmhf_info.svi_data`
- ADI Descriptions/Schemas: `{GCP_PROJECT}.nmhf_info.adi_data`
- Also use search_nmhf_documents for any definition/concept question — it covers all tables and acronyms.

DATASET 2: `{NMHF_DATA_DATASET}` (actual data statistics)
*CRITICAL*: Table names in this dataset often contain spaces and year/geography suffixes
(e.g. `ADI 2019`, `SVI 2020 County Level`, `NDI 2020`). You MUST wrap fully qualified table
names in backticks in your SQL (e.g. SELECT * FROM `{GCP_PROJECT}.{NMHF_DATA_DATASET}.ADI 2019` LIMIT 5).

CRITICAL ROUTING RULE — applies to EVERY category (ADI, SVI, NDI, AQI, or anything else),
not just ADI and SVI:
1. When the user asks for statistics/data on any topic, do NOT guess a table name and do NOT
   call query_nmhf_data immediately.
2. First call list_tables_for_category with the topic name (e.g. "ADI", "NDI", "SVI").
3. If it returns exactly one table, you may query it directly.
4. If it returns multiple tables, list the options back to the user in plain language
   (e.g. "I see NDI tables for 2019 and 2020 — which would you like?") and wait for their
   answer before calling query_nmhf_data.
5. If it returns no tables, tell the user honestly that you couldn't find a matching data
   table, and suggest they check search_nmhf_documents for related definitions instead.

DEFINITIONS: If the user asks for a definition, meaning, or "what is X", call
search_nmhf_documents rather than querying nmhf_info tables directly with SQL.

When answering, synthesize the information from your tools into a natural, easy-to-read,
conversational response. Never expose raw tool names or internal reasoning to the user.
"""

# =========================================================
# 7. THE MAIN CHAT LOOP
# =========================================================
st.title("NMHF Data Assistant")
st.markdown("Ask me for NMHF definitions or to pull specific data points from our database.")

if _embedding_model is None:
    st.warning(
        "Knowledge base index not found (nmhf_faiss.index / nmhf_metadata.json). "
        "Run build_faiss_index.py and place the output files next to this app "
        "for definition search to work. Data queries will still work."
    )

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Ask about NMHF data..."):
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Decide, deterministically, whether this is an appropriate moment to let
    # the model mention NMHF/SDOH equivalence: the first time legacy
    # terminology shows up, then again every 5th time after that — not
    # every single time the user says SDOH/social determinants.
    terminology_note = (
        "[Note to assistant: do not bring up the NMHF/SDOH terminology relationship "
        "in this reply unless the user directly asks about it.]"
    )
    if _uses_legacy_terminology(user_input):
        st.session_state.legacy_term_hits += 1
        hits = st.session_state.legacy_term_hits
        if hits == 1 or hits % 5 == 0:
            terminology_note = (
                "[Note to assistant: the user just used older terminology (SDOH / social "
                "determinants). This is a good, natural moment to briefly mention — in one "
                "casual sentence, not a correction — that NMHF (Non-Medical Health Factors) "
                "is the newer name for the same thing. Don't repeat this in your next "
                "several replies.]"
            )

    # This note is appended to the latest user turn only (not stored in
    # chat_history), so it guides this one response without cluttering the
    # visible conversation or being replayed as if the user wrote it.
    formatted_history = [
        genai_types.Content(role=msg["role"], parts=[genai_types.Part.from_text(text=msg["content"])])
        for msg in st.session_state.chat_history[:-1]
    ]
    formatted_history.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=f"{user_input}\n\n{terminology_note}")]
        )
    )

    with st.spinner("Searching Knowledge Base & Database..."):
        try:
            resp = genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=formatted_history,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[search_nmhf_documents, list_tables_for_category, query_nmhf_data],
                    temperature=0.1,
                ),
            )
            reply = resp.text
        except Exception as e:
            reply = f"I encountered an error processing your request: {e}"

    with st.chat_message("model"):
        st.markdown(reply)

    st.session_state.chat_history.append({"role": "model", "content": reply})
