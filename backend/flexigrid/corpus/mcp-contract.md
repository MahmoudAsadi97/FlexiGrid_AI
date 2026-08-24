---
id: mcp-contract
title: FlexiGrid tool contracts — what each MCP tool guarantees
source_type: project-doc
tags: mcp, tools, contract, agent, protocol
---

## Why typed tools

FlexiGrid exposes its data and planning functions to language models through the Model Context Protocol. Each tool declares a typed input schema and returns structured JSON, so a host application or examiner can inspect exactly what the model asked for and what it received. Nothing about the grid, the corpus, or the optimizer lives inside a prompt.

## The tool set

get_grid_snapshot returns the tariff and stress series with provenance. retrieve_evidence performs ranked retrieval over this corpus and returns chunk identifiers, titles, text, and scores. extract_constraints turns a natural-language mission into typed tasks and limits. optimize_schedule runs the deterministic constrained search over supplied tasks. validate_schedule re-checks any schedule against time windows and the capacity cap and is the final authority on feasibility.

## Guarantees

Tools are read-only with respect to the physical world: no tool commands a device. The optimizer and validator are deterministic: identical inputs give identical outputs. The retrieval tool's chunk identifiers are stable across a corpus version, which makes citations reproducible and lets the backend reject any citation that was not actually retrieved.
