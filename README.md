# gripe-mcp

Agent complaint box — one-tool MCP for logging bugs and improvement requests.

## One tool: `report_issue`

Call it when you guess, hit a missing tool, find bad docs, or produce uncertain
output. Non-blocking — log and continue.

| Param | Type | Description |
|---|---|---|
| `description` | str | What went wrong or what you'd like improved (max 200 chars) |
| `severity` | `low` / `medium` / `high` | low = friction, medium = guessed, high = abandoned/wrong |
| `section` | str | Which instruction or tool caused the issue (max 80 chars) |
| `mode` | enum | `ambiguous_instruction` `missing_tool` `bad_tool_doc` `hallucination_risk` `wrong_scope` `memory_miss` `other` |

## Storage

- **Postgres**: set `GRIPE_DB_URL` env var → single `gripe_issues` table
- **JSONL fallback**: timestamped files in `.gripe-mcp/` (one per day)

## Identity

`GRIPE_AGENT_ID` and `GRIPE_TASK_ID` are set at server startup via env vars.
The agent never self-reports identity.

## System prompt block

```
## Self-Monitoring

Use `report_issue` any time you guess, hit a missing tool, or produce output
you're uncertain about. Non-blocking — log and continue, no response expected.
There is no penalty for logging; silence is the failure mode we're trying to
prevent.
```

## Run

```bash
GRIPE_AGENT_ID=precis GRIPE_TASK_ID=review-123 gripe
```
