"""Environment self-check: verify the local stack before a demo.

    cd backend && python -m flexigrid.doctor

Checks, in order: corpus ingestion, retrieval (lexical + dense with the
resolved embedding backend), the Elia adapter (frozen fixture), the LLM
endpoint (models list + one structured smoke prompt), intent extraction, the
full agent pipeline, and an MCP stdio round-trip. Exits non-zero if a
critical check fails; prints an actionable hint for every failure.
"""

from __future__ import annotations

import asyncio
import sys
import time

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _report(name: str, ok: bool, detail: str, critical: bool = True) -> bool:
    mark = f"{GREEN}PASS{RESET}" if ok else (
        f"{RED}FAIL{RESET}" if critical else f"{YELLOW}WARN{RESET}")
    print(f"  [{mark}] {name:<28} {detail}")
    return ok or not critical


def main() -> int:
    print("FlexiGrid doctor\n")
    healthy = True

    # 1. corpus -----------------------------------------------------------
    try:
        from .ingest import load_corpus
        chunks = load_corpus()
        docs = len({chunk.doc_id for chunk in chunks})
        healthy &= _report("Corpus", True, f"{len(chunks)} chunks / {docs} docs")
    except Exception as error:
        healthy &= _report("Corpus", False, str(error))
        print("\nCorpus is required; aborting.")
        return 1

    # 2. retrieval --------------------------------------------------------
    try:
        from .retrieval import get_index
        index = get_index()
        lexical = index.retrieve("charge the EV in eco mode", mode="bm25")
        ok = lexical and lexical[0]["doc_id"] == "manual-ev"
        healthy &= _report("BM25 retrieval", bool(ok),
                           f"top hit: {lexical[0]['chunk_id']}")
    except Exception as error:
        healthy &= _report("BM25 retrieval", False, str(error))

    try:
        backend = get_index().backend
        started = time.perf_counter()
        dense = get_index().retrieve("charge the EV in eco mode", mode="dense")
        elapsed = int((time.perf_counter() - started) * 1000)
        healthy &= _report("Dense retrieval", bool(dense),
                           f"backend={backend.name} ({backend.model}), {elapsed} ms")
        if backend.name == "tfidf":
            print(f"         {YELLOW}hint{RESET}: neural embeddings unavailable — "
                  "start Ollama and `ollama pull nomic-embed-text`, or "
                  "`pip install sentence-transformers`")
    except Exception as error:
        healthy &= _report("Dense retrieval", False, str(error))

    # 3. Elia adapter -----------------------------------------------------
    try:
        from .elia_client import EliaClient
        tariff, stress, mode = EliaClient().series(use_live=False)
        ok = len(tariff) == 24 and len(stress) == 24
        healthy &= _report("Elia adapter (frozen)", ok, f"mode={mode}")
    except Exception as error:
        healthy &= _report("Elia adapter (frozen)", False, str(error))

    # 4. LLM endpoint -----------------------------------------------------
    from .llm import get_llm
    llm = get_llm()
    live = llm.available()
    detail = f"{llm.config.base_url} → {llm.config.model}"
    if not live:
        _report("LLM endpoint", False, f"{detail} — unreachable", critical=False)
        print(f"         {YELLOW}hint{RESET}: install Ollama, then "
              f"`ollama pull {llm.config.model}` and `ollama serve`. "
              "The pipeline still runs deterministically without it.")
    else:
        _report("LLM endpoint", True, detail)
        try:
            models = llm.list_models()
            present = any(llm.config.model.split(":")[0] in name for name in models)
            _report("Model present", present,
                    f"{len(models)} models listed", critical=False)
            if not present:
                print(f"         {YELLOW}hint{RESET}: `ollama pull {llm.config.model}`")
        except Exception as error:  # noqa: BLE001
            _report("Model present", False, str(error), critical=False)

        from .models import AgentDecision
        started = time.perf_counter()
        decision, notes = llm.structured(
            AgentDecision,
            "You are the planning agent of FlexiGrid. Choose the next tool.",
            "Tool catalog:\n- get_grid_snapshot: grid data\n\nCurrent state:\n"
            "constraints extracted: no\n\nChoose the next tool.",
            max_tokens=200)
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = decision is not None
        _report("Structured output", ok,
                f"{elapsed} ms, retries: {len(notes)}", critical=False)

    # 5. intent + agent + MCP --------------------------------------------
    try:
        from .intent import extract_intent
        result = extract_intent("Charge the EV before 07:00", llm=llm)
        ok = any(task.task_id == "ev" for task in result.spec.tasks)
        healthy &= _report("Intent extraction", ok, f"mode={result.mode}")
    except Exception as error:
        healthy &= _report("Intent extraction", False, str(error))

    try:
        from .agent import run_agent
        started = time.perf_counter()
        outcome = asyncio.run(run_agent(
            "Charge the EV and run the dishwasher before 07:00"))
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = outcome["plan"]["validation"]["valid"]
        healthy &= _report(
            "Agent pipeline", ok,
            f"{elapsed} ms, llm_live={outcome['modes']['llm_live']}, "
            f"steps={len(outcome['trace'])}")
    except Exception as error:
        healthy &= _report("Agent pipeline", False, str(error))

    try:
        from .mcp_host import run_agent_over_mcp
        started = time.perf_counter()
        outcome = asyncio.run(run_agent_over_mcp(
            "Run the laundry before 07:00", use_llm=False))
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = outcome["plan"]["validation"]["valid"] \
            and outcome["modes"]["transport"] == "mcp-stdio"
        healthy &= _report("MCP stdio round-trip", ok,
                           f"{elapsed} ms, tools="
                           f"{len(outcome['modes']['mcp_tools_listed'])}")
    except Exception as error:
        healthy &= _report("MCP stdio round-trip", False, str(error))

    print(f"\n{'All critical checks passed.' if healthy else 'Critical checks FAILED.'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
