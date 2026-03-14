"""
QueryMind Agents
Architecture: Sequential orchestrator → SQL Generator → Recovery Loop → Narrator + Chart
"""

import os
import json
from google.adk.agents import Agent, SequentialAgent, LoopAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

MODEL = "gemini-2.5-flash"
MCP_SERVER_PATH = os.path.join(os.path.dirname(__file__), "mcp_server.py")


# ── MCP Toolset ──────────────────────────────────────────────────────────────

def get_mcp_toolset():
    return MCPToolset(
        connection_params=StdioServerParameters(
            command="python",
            args=[MCP_SERVER_PATH],
        )
    )


# ── Agent 1: Schema Fetcher ───────────────────────────────────────────────────

schema_fetcher = Agent(
    name="schema_fetcher",
    model=MODEL,
    description="Fetches the BigQuery dataset schema so other agents know what tables and columns exist.",
    instruction="""
You are a schema discovery agent.

Call get_dataset_schema() to retrieve available tables and columns.
Output a concise schema summary in this format:

SCHEMA:
- table_name: col1 (TYPE), col2 (TYPE), ...

Do not generate SQL. Just report the schema clearly.
""",
    tools=[get_mcp_toolset()],
)


# ── Agent 2: SQL Generator ────────────────────────────────────────────────────

sql_generator = Agent(
    name="sql_generator",
    model=MODEL,
    description="Translates natural language questions into valid BigQuery SQL using the Medicare dataset.",
    instruction="""
You are a SQL generation agent for BigQuery.

You will receive:
1. A user question
2. A schema summary from the schema_fetcher

Your job: write a single, valid BigQuery Standard SQL SELECT query that answers the question.

Rules:
- Only use tables and columns that appear in the schema summary
- Always use fully qualified table names: `bigquery-public-data.cms_medicare.<table>`
- Use LIMIT 100 unless the question asks for aggregation
- Never use INSERT, UPDATE, DELETE, DROP, or any write operation
- Output ONLY the SQL — no explanation, no markdown fences

If the previous attempt failed, you will also receive the error message.
Fix the SQL based on the error before outputting.
""",
    tools=[get_mcp_toolset()],
)


# ── Agent 3: Query Executor + Recovery Loop ───────────────────────────────────

executor_agent = Agent(
    name="query_executor",
    model=MODEL,
    description="Executes SQL against BigQuery and signals success or failure for the retry loop.",
    instruction="""
You are a query execution agent.

1. Take the SQL from the previous agent's output (look for a SELECT statement).
2. Call run_bigquery_sql(sql=<the_sql>) to execute it.
3. If the result contains an "error" field that is not null:
   - Output exactly: EXECUTION_FAILED: <error message>
   - This signals the loop to retry with the sql_generator.
4. If successful (error is null):
   - Output: EXECUTION_SUCCESS
   - Then output the raw JSON result rows (first 20 rows max).
   - Format: RESULT_JSON: <json>

Be precise. The loop agent reads your output to decide whether to continue.
""",
    tools=[get_mcp_toolset()],
)

recovery_loop = LoopAgent(
    name="sql_recovery_loop",
    description="Retries SQL generation and execution up to 3 times on failure.",
    sub_agents=[sql_generator, executor_agent],
    max_iterations=3,
    # Loop exits when executor outputs EXECUTION_SUCCESS
    should_continue_fn=lambda output: "EXECUTION_SUCCESS" not in (output or ""),
)


# ── Agent 4: Narrator ─────────────────────────────────────────────────────────

narrator = Agent(
    name="narrator",
    model=MODEL,
    description="Converts raw BigQuery results into a plain-English insight summary and a chart specification.",
    instruction="""
You are a data insight narrator and chart designer.

You will receive raw BigQuery result rows (JSON) and the original user question.

Your output must be valid JSON with this exact structure:
{
  "summary": "<3-4 sentence plain English insight answering the user's question>",
  "chart": {
    "type": "bar" | "line" | "pie" | "table",
    "title": "<descriptive chart title>",
    "x_field": "<column name for x-axis or labels>",
    "y_field": "<column name for values>",
    "data": [<first 15 rows from result, as list of dicts>]
  },
  "key_finding": "<one bold headline finding, max 15 words>"
}

Choose chart type based on the data:
- Rankings / comparisons → bar
- Trends over time → line
- Proportions → pie (max 8 slices)
- Many columns → table

Output ONLY the JSON. No prose before or after.
""",
)


# ── Orchestrator ──────────────────────────────────────────────────────────────

orchestrator = SequentialAgent(
    name="querymind_orchestrator",
    description="QueryMind: Natural language data analyst for Medicare public data.",
    sub_agents=[
        schema_fetcher,
        recovery_loop,
        narrator,
    ],
)


# ── Runner ────────────────────────────────────────────────────────────────────

session_service = InMemorySessionService()
APP_NAME = "querymind"


def create_runner():
    return Runner(
        agent=orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )


async def run_query(question: str, session_id: str = "default") -> dict:
    """
    Run a natural language query through the full agent pipeline.
    Returns a dict with thinking_log (list of agent steps) and final output.
    """
    runner = create_runner()

    try:
        session_service.create_session(
            app_name=APP_NAME,
            user_id="user",
            session_id=session_id,
        )
    except Exception:
        pass  # session may already exist

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
            # Capture intermediate agent thinking
            agent_name = getattr(event, "author", "agent")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        thinking_log.append({
                            "agent": agent_name,
                            "step": part.text[:500],  # truncate for display
                        })

    # Try to parse narrator JSON output
    result = {"thinking_log": thinking_log, "raw_output": final_output}
    if final_output:
        try:
            # Strip markdown fences if present
            clean = final_output.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            result["summary"] = parsed.get("summary", "")
            result["key_finding"] = parsed.get("key_finding", "")
            result["chart"] = parsed.get("chart", {})
        except Exception:
            result["summary"] = final_output
            result["chart"] = {}

    return result
