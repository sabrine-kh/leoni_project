# Groq API key
import streamlit as st
import ast
import os
import time
import json
import unicodedata
import re
from io import StringIO
import contextlib
from supabase import create_client, Client
# from sentence_transformers import SentenceTransformer
import logging
import sys
import requests

# --- LangChain imports for agent-based routing ---
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain_groq import ChatGroq
from groq import Groq
# Initialize Streamlit
st.set_page_config(
    page_title="LEOparts Chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    [data-testid='stSidebarNav'] {display: none;}
    
    /* Sidebar white background */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%) !important;
    }
    /* Button styling with blue theme */
    .stButton > button {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 12px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(30, 60, 114, 0.2);
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2a5298 0%, #4a90e2 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(30, 60, 114, 0.4);
    }
    </style>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.markdown("<h2 style='color:white;'>Navigation</h2>", unsafe_allow_html=True)
    if st.button("🏠 Home"):
        st.switch_page("app.py")
    if st.button("💬 Chat with Leoparts"):
        st.switch_page("pages/chatbot.py")
    if st.button("📄 Extract a new Part"):
        st.switch_page("pages/extraction_attributs.py")
    if st.button("🆕 New conversation"):
        st.session_state.messages = []
        st.session_state.last_part_number = None
        st.rerun()
    if st.button("📊 Evaluate Doc Search"):
        st.switch_page("pages/evaluate_doc_search.py")

# Add navigation button at the top
if st.sidebar.button("← Back to Main App", use_container_width=True):
    st.switch_page("app.py")

# Add blue header band at the top
st.markdown(
    """
    <style>
    .header-band {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #4a90e2 100%);
        color: white;
        padding: 0.7rem 0;
        margin: -1rem -1rem 2rem -1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(30, 60, 114, 0.3);
    }
    .header-band h1 {
        font-size: 2.2em;
        margin: 0;
        font-weight: bold;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    </style>
    <div class="header-band">
        <h1>LEONI</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Configuration ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    HF_TOKEN = st.secrets["HF_TOKEN"]
    if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY, GROQ_API_KEY, HF_TOKEN]):
        raise ValueError("One or more secrets not found.")
except Exception as e:
    st.error(f"Error loading secrets: {e}")
    st.stop()

# --- Model & DB Config ---
MARKDOWN_TABLE_NAME = "markdown_chunks"
ATTRIBUTE_TABLE_NAME = "Leoni_attributes"          
RPC_FUNCTION_NAME = "match_markdown_chunks_1024"     
EMBEDDING_MODEL_NAME = "baai/bge-m3"  # Updated model name
EMBEDDING_DIMENSIONS = 1024  # Updated dimension for bge-m3

# ░░░  MODEL SWITCH  ░░░
GROQ_MODEL_FOR_SQL = "qwen/qwen3-32b"              
GROQ_MODEL_FOR_ANSWER = "qwen/qwen3-32b"             


# --- Search Parameters ---
VECTOR_SIMILARITY_THRESHOLD = 0.4
VECTOR_MATCH_COUNT = 3

# --- Initialize Clients ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    # st.success("Supabase client initialized.")
except Exception as e:
    st.error(f"Error initializing Supabase client: {e}")
    st.stop()

# Remove local SentenceTransformer loading
# from sentence_transformers import SentenceTransformer
# st_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
# test_emb = st_model.encode("test")
# if len(test_emb) != EMBEDDING_DIMENSIONS:
#     raise ValueError("Embedding dimension mismatch")

HF_API_URL = "https://hbaananou-embedder-model.hf.space/embed"  # Updated to custom endpoint
HF_TOKEN = st.secrets["HF_TOKEN"]

def get_query_embedding(text):
    if not text:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}"
        }
        payload = {
            "texts": [text]
        }
        print("Payload:", payload)
        response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=30)
        print("Status code:", response.status_code)
        print("Response text:", response.text)
        response.raise_for_status()
        result = response.json()
        # Use the correct key for your API
        if "vectors" in result:
            embedding = result["vectors"][0]
        elif "embedding" in result:
            embedding = result["embedding"]
        elif "embeddings" in result:
            embedding = result["embeddings"][0]
        else:
            raise ValueError("No embedding found in API response")
        return embedding
    except Exception as e:
        st.error(f"    Error generating query embedding via Hugging Face API: {e}")
        return None

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    st.error(f"Error initializing Groq client: {e}")
    st.stop()

# ───────────────────────────────────────────────────────────────────────────
# HELPER TO STRIP <think> … </think> FROM GROQ RESPONSES
# ───────────────────────────────────────────────────────────────────────────
def strip_think_tags(text: str) -> str:
    """
    Removes any <think> … </think> block (case-insensitive, single or multiline)
    that the reasoning model may prepend to its answer.
    """
    if not text:
        return text
    return re.sub(r'<\s*think\s*>.*?<\s*/\s*think\s*>',
                  '',
                  text,
                  flags=re.IGNORECASE | re.DOTALL).strip()

# ───────────────────────────────────────────────────────────────────────────
# Existing helper functions
# ───────────────────────────────────────────────────────────────────────────
def find_relevant_attributes_with_sql(generated_sql: str):
    """
    Executes the LLM-generated SELECT via execute_readonly_sql().
    Always returns List[dict] rows.
    """
    if not generated_sql:
        return []

    sql_to_run = generated_sql.rstrip().rstrip(';')
    try:
        res = supabase.rpc("execute_readonly_sql", {"q": sql_to_run}).execute()

        if not res.data:
            return []

        # If each element is already a dict, just return the list as-is
        if isinstance(res.data[0], dict):
            return res.data

        # Otherwise grab the single JSON column
        first_key = next(iter(res.data[0].keys()))
        return [_to_dict(row[first_key]) for row in res.data]

    except Exception as e:
        return []

# ───────────────────────────────────────────────────────────────────────────
#  TEXT-TO-SQL GENERATION
# ───────────────────────────────────────────────────────────────────────────
def generate_sql_from_query(user_query, table_schema):
    """Uses Groq LLM with refined prompt and examples to generate SQL, attempting broad keyword matching."""
    # --- Full Original Prompt ---
    prompt = f"""Your task is to convert natural language questions into robust PostgreSQL SELECT queries for the "Leoni_attributes" table. The primary goal is to find matching rows even if the user slightly misspells a keyword or uses variations.

Strictly adhere to the following rules:
1. **Output Only SQL or NO_SQL**: Your entire response must be either a single, valid PostgreSQL SELECT statement ending with a semicolon (;) OR the exact word NO_SQL if the question cannot be answered by querying the table. Do not add explanations or markdown formatting.

2. **Target Table**: ONLY query the "Leoni_attributes" table.

3. **Column Quoting**: Use double quotes around column names ONLY if necessary (contain spaces, capitals beyond first letter, special chars). Check schema: {table_schema}

4. **SELECT Clause**:
   - If the user asks for specific attributes (e.g., Colour, Mechanical Coding), include only those columns and the "Number" column.
   - If the user does not specify any particular attribute, include key informative columns like "Number", "Name", "Material Name", and "Sourcing Status".
   - Use `SELECT *` only when the user explicitly asks for "all data", "full info", or says "everything" about a part.
   - Always include columns referenced in the WHERE clause.

5. **Robust Keyword Searching (CRITICAL RULE)**:
   - Identify the main descriptive keyword(s) in the user's question (e.g., colors, materials, types like 'black', 'connector', 'grey', 'terminal'). Do NOT apply this robust search to specific identifiers like part numbers unless the user query implies a pattern search (e.g., 'starts with...').
   - For the identified keyword(s), generate a comprehensive list of **potential variations**:
     - **Common Abbreviations:** (e.g., 'blk', 'bk' for black; 'gry', 'gy' for grey; 'conn' for connector; 'term' for terminal).
     - **Alternative Spellings/Regional Variations:** (e.g., 'grey'/'gray', 'colour'/'color').
     - **Different Casings:** (e.g., 'BLK', 'Gry', 'CONN').
     - ***Likely Typos/Common Misspellings:*** (e.g., for 'black', consider 'blak', 'blck'; for 'terminal', consider 'termnial', 'terminl'; for 'connector', 'conecter'). Use your knowledge of common typing errors, but be reasonable – don't include highly improbable variations.
   - Search for the original keyword AND **ALL generated variations** across **multiple relevant text-based attributes**. Relevant attributes typically include "Colour", "Name", "Material Name", "Context", "Type Of Connector", "Terminal Position Assurance", etc. – use context to decide which columns are most relevant for the specific keyword.
   - Use `ILIKE` with surrounding wildcards (`%`) (e.g., `'%variation%'`) for case-insensitive, substring matching for every term and variation.
   - Combine **ALL** these individual search conditions (original + all variations across all relevant columns) using the `OR` operator. This might result in a long WHERE clause, which is expected.

6. **LIMIT Clause**:
   - Use `LIMIT 3` for specific part number lookups.
   - Use `LIMIT 10` or `LIMIT 20` for broad queries.

7. **YEAR FILTERS**:
   - If the user query contains a four-digit number between 1900–2100, filter on `EXTRACT(YEAR FROM "Created On") = <year>`.

8. **NO_SQL**:
   - Return `NO_SQL` for general definitions, non-database questions, or ambiguous queries.

9. **Ambiguous or Unclear Questions**:
   - If you are unsure which columns to select, or if the user's question is ambiguous, use SELECT * to return all columns for the matching rows.

10. **No Specific Column Mentioned**:
    - If the user question does not mention a specific column name or attribute, use SELECT * to return all columns for the matching rows.

Table Schema: "Leoni_attributes"
{table_schema}

Examples:

User Question: "What is part number P00001636?"
SQL Query: SELECT "Number", "Name", "Sourcing Status" FROM "Leoni_attributes" WHERE "Number" = 'P00001636' LIMIT 3;

User Question: "Give me all data about part P00001636"
SQL Query: SELECT * FROM "Leoni_attributes" WHERE "Number" = 'P00001636' LIMIT 3;

User Question: "What is the Colour of part P00108815?"
SQL Query: SELECT "Number", "Colour" FROM "Leoni_attributes" WHERE "Number" = 'P00108815' LIMIT 3;

User Question: "Show me parts containing connector"
SQL Query: SELECT "Number", "Name", "Type Of Connector" FROM "Leoni_attributes" WHERE "Name" ILIKE '%connector%' OR "Name" ILIKE '%conn%' OR "Type Of Connector" ILIKE '%connector%' OR "Type Of Connector" ILIKE '%conn%' LIMIT 10;

User Question: "Which parts are grey"
SQL Query: SELECT "Number", "Colour", "Name" FROM "Leoni_attributes" WHERE "Colour" ILIKE '%grey%' OR "Colour" ILIKE '%gry%' OR "Name" ILIKE '%grey%' OR "Name" ILIKE '%gry%' LIMIT 10;

User Question: "Is this part number P00739119 is GF?"
SQL Query: SELECT "Number", "Material Filling" FROM "Leoni_attributes" WHERE "Number" = 'P00739119' AND "Material Filling" ILIKE '%GF%' LIMIT 3;

User Question: "Give me the list of part numbers created in 2021"
SQL Query: SELECT "Number", "Created On" FROM "Leoni_attributes" WHERE EXTRACT(YEAR FROM "Created On") = 2021 LIMIT 20;

User Question: "{user_query}"
SQL Query:
"""
    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an expert Text-to-SQL assistant generating PostgreSQL queries optimized for finding matches despite keyword variations and typos."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL_FOR_SQL,
            temperature=0.1,
            max_tokens=40960
        )
        if not response.choices or not response.choices[0].message:
            return None

        # ░░░ STRIP REASONING BLOCK FIRST ░░░
        generated_sql = strip_think_tags(response.choices[0].message.content)

        if generated_sql == "NO_SQL":
            return None

        # Check if valid SQL (starts with SELECT, ends with ;)
        if generated_sql.upper().startswith("SELECT") and generated_sql.rstrip().endswith(';'):
            forbidden = ["UPDATE", "DELETE", "INSERT", "DROP", "TRUNCATE",
                         "ALTER", "CREATE", "EXECUTE", "GRANT", "REVOKE"]
            pattern = re.compile(r'\b(?:' + '|'.join(forbidden) + r')\b', re.IGNORECASE)
            if pattern.search(generated_sql):
                return None

            # Check if the target table name appears after FROM
            table_name_pattern = r'FROM\s+(?:[\w]+\.)?("?' + ATTRIBUTE_TABLE_NAME + r'"?)'
            if not re.search(table_name_pattern, generated_sql, re.IGNORECASE):
                return None

            return generated_sql
        else:
            return None
    except Exception as e:
        return None

# ───────────────────────────────────────────────────────────────────────────
#  SQL EXECUTION FUNCTION
# ───────────────────────────────────────────────────────────────────────────
def _to_dict(maybe_json):
    """
    Ensure the value is a Python dict. Decode JSON/JSONB strings if needed.
    """
    if isinstance(maybe_json, dict):
        return maybe_json
    if isinstance(maybe_json, str):
        # Try fast JSON decode first
        try:
            return json.loads(maybe_json)
        except json.JSONDecodeError:
            pass
        # Fallback: literal_eval handles single quotes, etc.
        try:
            return ast.literal_eval(maybe_json)
        except Exception:
            pass
    # Give up – return an empty dict to avoid crashing format_context
    return {}

# ───────────────────────────────────────────────────────────────────────────
#  CONTEXT FORMATTING
# ───────────────────────────────────────────────────────────────────────────
def format_context(attribute_rows):
    if not attribute_rows:
        return "No relevant information found in the knowledge base (attributes)."
    # If only one row, show as a vertical table (attribute | value)
    if len(attribute_rows) == 1:
        row = attribute_rows[0]
        table = "| Attribute | Value |\n|---|---|\n"
        for key, value in row.items():
            display_value = "None" if value is None or value == "" else json.dumps(value)
            table += f"| {key} | {display_value} |\n"
        return table
    # If multiple rows, show as a horizontal table
    headers = list(attribute_rows[0].keys())
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join("---" for _ in headers) + " |\n"
    for row in attribute_rows:
        table += "| " + " | ".join(
            "None" if row.get(h, None) is None or row.get(h, "") == "" else json.dumps(row.get(h, ""))
            for h in headers
        ) + " |\n"
    return table

# ───────────────────────────────────────────────────────────────────────────
#  CHAT COMPLETION FOR ANSWERS
# ───────────────────────────────────────────────────────────────────────────
def get_groq_chat_response(prompt, context_provided=True):
    if context_provided:
        system_message = (
            "You are a helpful assistant knowledgeable about LEOparts standards and attributes. "
            "When answering questions using database attributes, always start with a short, clear sentence summarizing the key answer. "
            "Then, present the relevant data as a markdown table with column headers matching the database columns. "
            "IMPORTANT: When the database returns part numbers (especially for date-based queries), present them clearly. "
            "Do not say information is not available if part numbers are returned. "
            "For date-based queries, format the response as: 'Here are the part numbers [created/modified] in [year]: [list of part numbers]' "
            "When answering questions about definitions or concepts from documentation, provide clear, concise explanations without mentioning database attributes. "
            "Do not add any extra explanations or formatting."
        )
    else:
        system_message = ("You are a helpful assistant knowledgeable about LEOparts standards and attributes. "
                          "You were unable to find relevant information in the knowledge base (documents or attributes) to answer the user's question. "
                          "State clearly that the information is not available in the provided materials. Do not make up information or answer from general knowledge.")

    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL_FOR_ANSWER,
            temperature=0.1,
            stream=False
        )
        raw_reply = response.choices[0].message.content
        return strip_think_tags(raw_reply)
    except Exception as e:
        st.error(f"    Error calling Groq API: {e}")
        return "Error contacting LLM."

# ───────────────────────────────────────────────────────────────────────────
#  VECTOR SEARCH FOR MARKDOWN CHUNKS
# ───────────────────────────────────────────────────────────────────────────
def find_relevant_markdown_chunks(user_query: str, limit: int = 5):
    """
    Searches for relevant markdown chunks using vector similarity.
    Returns List[dict] with chunk content and metadata.
    """
    if not user_query:
        return []
    
    try:
        # Generate embedding for the query
        query_embedding = get_query_embedding(user_query)
        if not query_embedding:
            return []
        
        # Call the RPC function to find similar chunks
        response = supabase.rpc(
            RPC_FUNCTION_NAME,
            {
                "query_embedding": query_embedding,
                "match_threshold": VECTOR_SIMILARITY_THRESHOLD,
                "match_count": limit
            }
        ).execute()
        
        if not response.data:
            return []
        
        return response.data
        
    except Exception as e:
        st.error(f"Error searching markdown chunks: {e}")
        return []

def format_markdown_context(markdown_chunks):
    """Formats markdown chunks into a readable context string, filtering out navigation links."""
    if not markdown_chunks:
        return "No relevant markdown content found."
    context_parts = []
    for i, chunk in enumerate(markdown_chunks):
        content = chunk.get('content', '')
        source = chunk.get('source', 'Unknown')
        page = chunk.get('page', 'N/A')
        # Remove navigation links like 'back to Table of Content' (case-insensitive)
        filtered_lines = [
            line for line in content.splitlines()
            if 'back to table of content' not in line.lower()
            and 'back to contents' not in line.lower()
            and 'table of content' not in line.lower()
        ]
        filtered_content = '\n'.join(filtered_lines)
        context_parts.append(f"--- Markdown Chunk {i+1} (Source: {source}, Page: {page}) ---\n{filtered_content}")
    return "\n\n".join(context_parts)

# ───────────────────────────────────────────────────────────────────────────
#  MAIN CHAT LOOP
# ───────────────────────────────────────────────────────────────────────────

leoni_attributes_schema_for_main_loop = """(id: bigint, Number: text, Name: text, "Object Type Indicator": text, Context: text, Version: text, State: text, "Last Modified": timestamp with time zone, "Created On": timestamp with time zone, "Sourcing Status": text, "Material Filling": text, "Material Name": text, "Max. Working Temperature [°C]": numeric, "Min. Working Temperature [°C]": numeric, Colour: text, "Contact Systems": text, Gender: text, "Housing Seal": text, "HV Qualified": text, "Length [mm]": numeric, "Mechanical Coding": text, "Number Of Cavities": numeric, "Number Of Rows": numeric, "Pre-assembled": text, Sealing: text, "Sealing Class": text, "Terminal Position Assurance": text, "Type Of Connector": text, "Width [mm]": numeric, "Wire Seal": text, "Connector Position Assurance": text, "Colour Coding": text, "Set/Kit": text, "Name Of Closed Cavities": text, "Pull-To-Seat": text, "Height [mm]": numeric, Classification: text)"""

def extract_part_number(text):
    """Extrait un numéro de pièce commençant par P et suivi de chiffres (ex: P00739119)"""
    match = re.search(r'\bP\d{8,}\b', text)
    if match:
        return match.group(0)
    return None

# --- Initialize LangChain LLM (Qwen via Groq) ---
llm = ChatGroq(
    temperature=0.0,
    groq_api_key=GROQ_API_KEY,
    model_name=GROQ_MODEL_FOR_SQL,  # Use your Qwen model
    max_tokens=8069,
    
)

# Configure logging to stdout
logging.basicConfig(
    stream=sys.stdout,  # <-- This sends logs to the console, visible in Streamlit Cloud logs
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# --- LLM-based tool classifier ---
def llm_choose_tool(question, llm):
    prompt = (
        "You are a router for a chatbot. "
        "Given the following user question, decide which tool should be used to answer it. "
        "If the question is about specific part numbers, attributes, or database lookups (like 'What is the color of part P123456?'), answer 'SQL'. "
        "If the question is about definitions, explanations, concepts, or general knowledge (like 'What is Number Of Fuse-Circuits?'), answer 'VECTOR'. "
        "Answer with only 'SQL' or 'VECTOR'.\n\n"
        f"User question: {question}\nTool:"
    )
    logging.info(f"[LOG] LLM routing prompt: {prompt}")
    response = llm.invoke(prompt) if hasattr(llm, 'invoke') else llm(prompt)
    logging.info(f"[LOG] LLM routing response: {response}")
    if hasattr(response, "content"):
        answer_text = response.content
    else:
        answer_text = str(response)
    answer = answer_text.strip().upper()
    if "SQL" in answer:
        return "sql"
    elif "VECTOR" in answer:
        return "vector"
    else:
        return "vector"  # default fallback

def run_chatbot():
    st.title("🤖 Welcome to Leoni Chatbot")
    st.markdown("Ask questions about the extracted data.")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_part_number" not in st.session_state:
        st.session_state.last_part_number = None
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if prompt := st.chat_input("What would you like to know?"):
        part_number = extract_part_number(prompt)
        if part_number:
            st.session_state.last_part_number = part_number
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                logging.info(f"[LOG] User question: {prompt}")
                tool_choice = llm_choose_tool(prompt, llm)
                logging.info(f"[LOG] LLM tool choice: {tool_choice}")
                relevant_attribute_rows = []
                relevant_markdown_chunks = []
                context_was_found = False
                generated_sql = None
                if tool_choice == "sql":
                    prompt_for_sql = prompt
                    if (
                        ("part number" in prompt.lower() or "state" in prompt.lower() or "approved" in prompt.lower() or "sourcing status" in prompt.lower())
                        and not extract_part_number(prompt)
                        and st.session_state.last_part_number
                    ):
                        prompt_for_sql = f"{prompt} (about part number {st.session_state.last_part_number})"
                    generated_sql = generate_sql_from_query(prompt_for_sql, leoni_attributes_schema_for_main_loop)
                    logging.info(f"[LOG] Generated SQL: {generated_sql}")
                    if generated_sql:
                        relevant_attribute_rows = find_relevant_attributes_with_sql(generated_sql)
                        logging.info(f"[LOG] SQL tool returned rows: {len(relevant_attribute_rows)}")
                        context_was_found = bool(relevant_attribute_rows)
                    # Only add markdown context if no SQL results found
                    if not relevant_attribute_rows:
                        relevant_markdown_chunks = find_relevant_markdown_chunks(prompt, limit=3)
                        logging.info(f"[LOG] Vector tool (fallback) returned chunks: {len(relevant_markdown_chunks)}")
                        if relevant_markdown_chunks:
                            context_was_found = True
                else:
                    relevant_markdown_chunks = find_relevant_markdown_chunks(prompt, limit=3)
                    logging.info(f"[LOG] Vector tool returned chunks: {len(relevant_markdown_chunks)}")
                    context_was_found = bool(relevant_markdown_chunks)
                attribute_context = format_context(relevant_attribute_rows)
                markdown_context = format_markdown_context(relevant_markdown_chunks)
                combined_context = ""
                if relevant_attribute_rows:
                    combined_context += f"**Database Attributes Information:**\n{attribute_context}\n\n"
                if relevant_markdown_chunks:
                    combined_context += f"**Documentation/Standards Information:**\n{markdown_context}\n\n"
                if not combined_context:
                    combined_context = "No relevant information found in the knowledge base (attributes or documentation)."
                logging.info(f"[LOG] Final context sent to LLM:\n{combined_context}")
                history = ""
                for message in st.session_state.messages[-10:-1]:
                    role = "User" if message["role"] == "user" else "Assistant"
                    history += f"{role}: {message['content']}\n"
                # Add conditional instruction for table vs. plain text
                if relevant_attribute_rows:
                    extra_instruction = (
                        "Present your answer as a clear, concise sentence, followed by the table if relevant. "
                        "Do not add any meta-comments or explanations about where the data comes from. "
                        "Do not mention that information is not available in the database if you have found relevant data.\n"
                    )
                else:
                    extra_instruction = (
                        "Present your answer as a clear, concise sentence based on the documentation provided. "
                        "Do not add any meta-comments or explanations about where the data comes from. "
                        "Do not mention database attributes or say information is not available in the database.\n"
                    )
                extra_instruction += (
    "If an attribute value is None, null, or empty, display it as None (not as 'Not provided' or any other phrase). "
    "Do not paraphrase or summarize missing values. Always use the exact value as shown in the table.\n"
)
                prompt_for_llm = f"""Context:
{combined_context}

Conversation history:
{history}
User Question: {prompt}

When answering, always use the conversation history to resolve references (such as pronouns or phrases like 'this part number') to the correct entities mentioned earlier. 
Answer the user question based *only* on the provided context and the conversation history. 
{extra_instruction}When using documentation context, quote or closely follow the original wording and structure whenever possible. 
Only summarize or paraphrase when necessary for clarity, and do not add information not present in the context.
"""
                llm_response = get_groq_chat_response(prompt_for_llm, context_provided=context_was_found)
                st.markdown(llm_response)
                st.session_state.messages.append({"role": "assistant", "content": llm_response})
                print("Contexte envoyé au modèle :")
                print(combined_context)

# The chatbot will be called from app.py
if __name__ == "__main__":
    run_chatbot() 