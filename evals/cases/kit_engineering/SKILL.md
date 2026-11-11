---
name: kit-member-query
description: >-
  Query the deployed semantic layer. Trust the handshake tool list as the live
  source of truth; do not copy a frozen tool table into the session.
license: Apache-2.0
---

# Kit member query

Query a running deployment. Prefer MCP for reads.

The handshake tool list is the live source of truth. Do not copy a tool table
into the session; if the handshake and this skill disagree, trust the handshake.

## Instructions

1. check readiness first.
2. Ask through MCP, or REST fallback.
3. Do not turn a read-only question into a mutation.
