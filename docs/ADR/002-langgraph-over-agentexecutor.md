# ADR-002: LangGraph over LangChain AgentExecutor

**Status:** Accepted  
**Date:** 2026-09

---

## Context

Two frameworks were evaluated for the agent loop: LangChain's `AgentExecutor` and LangGraph's `StateGraph`. Both run tool-calling loops, handle retries, and integrate with the same LLM providers.

The agent needs to do more than call tools in a loop. It needs to:
- make a real routing decision (structured fact vs prose retrieval) that changes control flow
- reflect on retrieved context and conditionally retry with a reformulated query
- verify claims with a different model than the generator
- persist every node transition for debugging

---

## Decision

Use **LangGraph** `StateGraph` with explicit nodes and conditional edges.

---

## Alternatives Considered

**LangChain AgentExecutor.**  
Rejected. `AgentExecutor` is a black-box ReAct loop: the LLM decides what to call next, the framework calls it, repeat. Control flow is inside the LLM's generation, not in code. This makes the routing decision (structured fact vs RAG) unenforceable — the model could route a CVE question to retrieval and the framework would comply. More practically, `AgentExecutor` has no native support for conditional branching, reflection loops with a cap, or multi-node state snapshots. Debugging a misbehaving run means reading a dense log; with LangGraph you replay the state snapshot from the database.

**Custom asyncio loop.**  
Considered. A hand-rolled loop would have full control but loses LangGraph's compiled graph validation, built-in streaming, and Langsmith tracing integration. The implementation cost is higher for no practical benefit at this scale.

**Prefect / Temporal workflow engine.**  
Rejected as massively over-engineered. A 14-day build does not need a distributed workflow engine. LangGraph's in-process state machine is sufficient.

---

## Consequences

- Every node is a plain Python function with a typed `AgentState` in and `AgentState` out. Unit tests mock the LLM and call the node function directly — no framework mocking needed.
- The conditional edges (`reflect → route` vs `reflect → synthesize`, `verify → synthesize` retry) are code, not prompt instructions, so they cannot be overridden by a confused model.
- The hard caps (MAX_REFLECTIONS=3, MAX_TOOL_CALLS=12) are enforced in the edge functions, not in prompts. A prompt saying "stop after 3 tries" is advisory; a Python `if` is not.
- LangGraph's `compiled.ainvoke()` returns the full final state, which is serialized to the `agent_runs` table for replay.
