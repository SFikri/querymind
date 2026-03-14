"""
QueryMind Agents - v2 (direct BigQuery tools, no MCP stdio issues)
Architecture: Sequential orchestrator -> Schema Fetcher -> SQL Recovery Loop -> Narrator
"""

# NEW
import os
import json
from google.adk.agents import Agent, SequentialAgent, LoopAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.cloud import bigquery

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

MODEL = "gemini-2.5-flash"
APP_NAME = "querymind"

bq_client = bigquery.Client()

BLOCKED_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "MERGE"]


def get_dataset_schema() -> dict:
    """Return available tables and columns in the Medicare dataset."""
    try:
        tables = list(bq_client.list_tables("bigquery-public-data.cms_medicare"))
        result = {}
        for table in tables[:8]:
            ref = bq_client.get_table(table)
            result[table.table_id] = [
                {"name": f.name, "type": f.field_type}
                for f in ref.schema
            ]
        return {"tables": result}
    except Exception as e:
        return {"error": str(e), "tables": {}}


def run_bigquery_sql(sql: str) -> dict:
    """Execute a read-only BigQuery SQL query. Returns rows or an error string."""
    sql_upper = sql.upper()
    for kw in BLOCKED_KEYWORDS:
        if kw in sql_upper:
            return {"error": f"Blocked: '{kw}' not permitted. Only SELECT allowed.", "rows": [], "row_count": 0}
    try:
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100 * 1024 * 1024)
        query_job = bq_client.query(sql, job_config=job_config)
        results = query_job.result(timeout=30)
        rows = [dict(row) for row in results][:200]
        return {
            "error": None,
            "rows": rows,
            "row_count": len(rows),
            "schema": [{"name": f.name, "type": f.field_type} for f in results.schema],
        }
    except Exception as e:
        return {"error": str(e), "rows": [], "row_count": 0}


schema_fetcher = Agent(
    name="schema_fetcher",
    model=MODEL,
    description="Fetches BigQuery dataset schema.",
    instruction="""
You are a schema discovery agent.
Call get_dataset_schema() and output:

SCHEMA:
- table_name: col1 (TYPE), col2 (TYPE), ...

Do not generate SQL.
""",
    tools=[get_dataset_schema],
)

sql_generator = Agent(
    name="sql_generator",
    model=MODEL,
    description="Translates natural language into BigQuery SQL.",
    instruction="""
You are a SQL generation agent for BigQuery.

You receive:
1. A user question
2. A schema summary
3. Optionally: a prior error to fix

Write ONE valid BigQuery Standard SQL SELECT query.
- Use fully qualified table names: `bigquery-public-data.cms_medicare.<table>`
- Use LIMIT 100 unless aggregating
- Never use INSERT, UPDATE, DELETE, DROP
- Output ONLY the SQL, no markdown, no explanation
""",
    tools=[],
)

executor_agent = Agent(
    name="query_executor",
    model=MODEL,
    description="Executes SQL via BigQuery and signals success or failure.",
    instruction="""
You are a query execution agent.

1. Find the SELECT statement in the previous output.
2. Call run_bigquery_sql(sql=<the_sql>).
3. If result has a non-null error field:
   - Output: EXECUTION_FAILED: <error>
4. If successful:
   - Output: EXECUTION_SUCCESS
   - Output: RESULT_JSON: <first 20 rows as JSON>
""",
    tools=[run_bigquery_sql],
)

recovery_loop = LoopAgent(
    name="sql_recovery_loop",
    description="Retries SQL generation and execution up to 3 times.",
    sub_agents=[sql_generator, executor_agent],
    max_iterations=3,
)

narrator = Agent(
    name="narrator",
    model=MODEL,
    description="Converts query results into insights and chart specs.",
    instruction="""
You are a data insight narrator.

You receive BigQuery result rows and the original user question.

Output ONLY valid JSON:
{
  "summary": "<3-4 sentence plain English insight>",
  "chart": {
    "type": "bar" or "line" or "pie" or "table",
    "title": "<title>",
    "x_field": "<column for x-axis or labels>",
    "y_field": "<column for values>",
    "data": [<first 15 rows>]
  },
  "key_finding": "<one headline, max 15 words>"
}

No prose before or after the JSON.
""",
)

orchestrator = SequentialAgent(
    name="querymind_orchestrator",
    description="QueryMind: NL data analyst for Medicare public data.",
    sub_agents=[schema_fetcher, recovery_loop, narrator],
)

session_service = InMemorySessionService()


async def run_query(question: str, session_id: str = "default") -> dict:
    runner = Runner(
        agent=orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )

    await session_service.create_session(
        app_name=APP_NAME,
        user_id="user",
        session_id=session_id,
    )

    thinking_log = []
    final_output = None

    async for event in runner.run_async(
        user_id="user",
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=question)],
        ),
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_output = event.content.parts[0].text
        else:
            agent_name = getattr(event, "author", "agent")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        thinking_log.append({
                            "agent": agent_name,
                            "step": part.text[:500],
                        })

    result = {"thinking_log": thinking_log, "raw_output": final_output}
    if final_output:
        try:
            clean = final_output.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            result["summary"] = parsed.get("summary", "")
            result["key_finding"] = parsed.get("key_finding", "")
            result["chart"] = parsed.get("chart", {})
        except Exception:
            result["summary"] = final_output
            result["chart"] = {}

    return result
