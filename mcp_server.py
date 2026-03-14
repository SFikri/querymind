"""
QueryMind MCP Server
Exposes BigQuery as an MCP tool for the ADK orchestrator.
Run: python mcp_server.py
"""

import json
from fastmcp import FastMCP
from google.cloud import bigquery

mcp = FastMCP("querymind-bq")
bq_client = bigquery.Client()

ALLOWED_DATASET = "bigquery-public-data.cms_medicare"

# Safety guardrail: block any write operations
BLOCKED_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "MERGE"]


def _is_safe_query(sql: str) -> tuple[bool, str]:
    sql_upper = sql.upper()
    for kw in BLOCKED_KEYWORDS:
        if kw in sql_upper:
            return False, f"Blocked: SQL contains forbidden keyword '{kw}'. Only SELECT queries are permitted."
    return True, ""


@mcp.tool()
def run_bigquery_sql(sql: str) -> dict:
    """
    Execute a read-only BigQuery SQL query against the Medicare public dataset.
    Returns rows as a list of dicts, capped at 500 rows.
    Raises an error string on failure so the recovery agent can retry.
    """
    safe, reason = _is_safe_query(sql)
    if not safe:
        return {"error": reason, "rows": [], "row_count": 0}

    try:
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=100 * 1024 * 1024  # 100 MB cap
        )
        query_job = bq_client.query(sql, job_config=job_config)
        results = query_job.result(timeout=30)
        rows = [dict(row) for row in results][:500]
        return {
            "error": None,
            "rows": rows,
            "row_count": len(rows),
            "schema": [{"name": f.name, "type": f.field_type} for f in results.schema],
        }
    except Exception as e:
        return {"error": str(e), "rows": [], "row_count": 0}


@mcp.tool()
def get_dataset_schema() -> dict:
    """
    Return the available tables and their schemas in the Medicare dataset.
    Use this before writing SQL to understand what columns exist.
    """
    try:
        tables = list(bq_client.list_tables("bigquery-public-data.cms_medicare"))
        result = {}
        for table in tables[:10]:  # cap at 10 tables
            ref = bq_client.get_table(table)
            result[table.table_id] = [
                {"name": f.name, "type": f.field_type, "description": f.description or ""}
                for f in ref.schema
            ]
        return {"tables": result}
    except Exception as e:
        return {"error": str(e), "tables": {}}


if __name__ == "__main__":
    mcp.run(transport="stdio")
