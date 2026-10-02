# FlexiGrid research-backed upgrade

Review date: 2 October 2026. Scope: household scheduling research prototype, not a deployed controller.

## Executive decision

The next useful step for this repository is a trustworthy optimization and evaluation layer, not a larger language model. The original separation between language interpretation and numerical planning is worth retaining. This upgrade makes the scheduling objective dimensionally correct, replaces enumeration with a mixed-integer formulation, adds explicit forecast-error reserves, and strengthens the boundary between model suggestions and executable tool arguments.

The result has two intentionally separate interfaces. The original mission interface remains an hourly, four-device advisory demonstration. The new Planning lab accepts explicit 15-, 30-, or 60-minute problems, variable appliance power profiles, background load and reserves. The advanced interface does not pretend that an hourly natural-language parser has acquired quarter-hour understanding.

The changes implement selected ideas, not complete reproductions of every paper below. No real-household cost reduction, model superiority, physical safety certification, or federated privacy guarantee is claimed.

## 1. Code audit and decisions

| Original issue | Why it matters | Implemented response |
| --- | --- | --- |
| Objective counted favorable hours without weighting appliance power | A cheap hour is more valuable for a 3.6 kW charger than a 0.5 kW appliance | Integrate power times slot duration times price or stress |
| `cost` mixed price and stress; normalization divided by maximum daily price | “Lowest cost” was not a pure monetary objective; zero and negative prices broke assumptions | Pure cost/grid modes; explicit fixed scale only for the balanced objective |
| Exhaustive search pruned when partial cost exceeded the incumbent | Negative future costs invalidate that pruning argument | MILP for use; bounded full enumeration and a separately implemented reference for testing |
| Validator trusted schedule-supplied duration, power and windows | A shortened task or a forged limit could pass the checker | Reconstruct advanced loads from the original request; bind the legacy final gate to the extracted mission |
| Model-supplied tool arguments could replace validation inputs | The component being checked could influence its own checks | State-owned planning and validation arguments, prerequisites, and a mandatory local final check |
| Hourly intent rounded deadlines up and could widen too-short windows | A plan could finish late or start earlier than the user requested | Rules round deadlines down, starts up, reject impossible windows and invalid clock times; sanitizer no longer widens windows |
| Capacity only counted flexible devices | It was not a whole-house import limit | Label legacy scope; advanced capacity includes forecast background and explicit reserve |
| Citation membership was called citation precision | A valid identifier does not establish that a source supports a claim | Label the metric citation ID validity; do not invent a fallback citation when retrieval is empty |
| No automated verification workflow | Regressions were easy to miss | Backend, MCP, frontend, type-check, source archive and benchmark jobs |

Remaining semantic limitation: the final legacy gate verifies the extracted specification, not the original sentence's meaning. The parser still has a narrow vocabulary, simplified shared time windows and catalog assumptions. It does not model requested room temperature, battery charge or drying. Inspect the specification. Use the explicit advanced request for meaningful scheduling experiments.

## 2. Research selection and implementation mapping

### A. Appliance scheduling with mixed-integer optimization

Bradac, Kaczmarczyk and Fiedler, *Optimal Scheduling of Domestic Appliances via MILP*, Energies 8(1), 217-232, DOI [10.3390/en8010217](https://doi.org/10.3390/en8010217). The issue is dated 2015; the publisher records online publication on 29 December 2014.

The paper formulates appliance scheduling with operating restrictions, tariffs and peak-power constraints. That is closely aligned with this repository's decision problem. We use a time-indexed start-variable formulation with fixed non-interruptible profiles. This is an independently written implementation, not a port of the paper's CPLEX model or a reproduction of its Czech tariff experiments.

**Implemented:** SciPy/HiGHS MILP, finite solve budget, original-request checker and explicit solver status. **Not implemented:** every appliance phase/interruption model in the paper, electricity-market settlement or a distribution-network power-flow model.

Why not immediately use deep reinforcement learning? For this explicit finite-horizon scheduling problem, constraints and costs are already known. MILP provides an inspectable reference and a meaningful bound. A learned policy should first demonstrate an advantage against this reference under equal information, realistic latency and out-of-sample conditions. This is an engineering selection for this repository, not a universal ranking of methods.

### B. Compound language-model planning with external verification

Gundawar et al., *Robust Planning with Compound LLM Architectures: An LLM-Modulo Approach* (2024), [arXiv:2411.14484](https://arxiv.org/abs/2411.14484).

The useful architectural principle is to place explicit verifiers around model-generated proposals. Any correctness claim remains conditional on the verifier and problem representation being complete and correct.

**Implemented:** trusted state owns specification, capacity, schedule, objective and validation arguments. The model may refine retrieval text and bounded retrieval depth. Required stages cannot be skipped, and a local gate rechecks the returned schedule even when an external executor says it is valid. Tests include malicious decision arguments and a forged external validation response.

**Not claimed:** formally verified Python, perfect intent extraction, universally injection-proof behavior, or factual correctness of all generated prose. A remote data source can still supply incorrect facts; numerical consistency and source truth are different concerns.

### C. Conformal prediction for an explicit reserve

Angelopoulos and Bates, *A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification*, [arXiv:2107.07511](https://arxiv.org/abs/2107.07511), first posted 2021. Zhou, Lindemann and Sesia, *Conformalized Adaptive Forecasting of Heterogeneous Trajectories*, ICML 2024, [PMLR 235](https://proceedings.mlr.press/v235/zhou24l.html).

Split-conformal calibration motivates a finite-sample order statistic. Trajectory forecasting motivates evaluating an entire horizon rather than presenting independent slot coverage as whole-day protection. This implementation uses a deliberately simple one-sided maximum residual per block; it does not reproduce Zhou et al.'s complete adaptive procedure.

**Implemented:** held-out forecast/actual blocks, finite-sample rank correction, a constant horizon reserve, shape and finite-value checks, and rejection when too little calibration data exists for a finite quantile.

**Not implemented:** a trained load forecaster, adaptive conformal methods, drift detection or automatic recalibration. Ordinary rolling time-series windows are not automatically exchangeable. Stocker et al., *A Gentle Introduction to Conformal Time Series Forecasting* (2025), [arXiv:2511.13608](https://arxiv.org/abs/2511.13608), discusses why temporal dependence and distribution shifts require additional care. The API reports these assumptions rather than promising unconditional safety.

### D. Citation quality and retrieval evaluation

Gao et al., *Enabling Large Language Models to Generate Text with Citations*, EMNLP 2023, [ACL Anthology](https://aclanthology.org/2023.emnlp-main.398/).

ALCE distinguishes aspects of answer correctness and citation support. An allow-list checks only whether the cited item was retrieved. It cannot establish entailment.

**Implemented:** corrected labels in API evaluation and dashboard, explicit metric scope, no invented citation on empty retrieval. The old `citation_precision` JSON key remains a compatibility alias.

**Next experiment, not implemented:** label individual claims and supporting passages; measure citation correctness and coverage, unsupported numeric statements, abstention and retrieval failure. Evaluate a cross-encoder reranker against the existing BM25/dense/RRF baseline on held-out queries before introducing a new model dependency. Do not tune on the same 40 queries used for reporting.

### E. Indirect prompt injection

Greshake et al., *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection* (2023), [arXiv:2302.12173](https://arxiv.org/abs/2302.12173).

Retrieved text must be treated as data, not authority to change scheduling limits or invoke arbitrary operations. The argument ownership change follows this separation. It reduces the tested attack surface but is not a complete security evaluation. Real deployment needs independent adversarial test sets, authentication, rate limits, provenance checks and operational monitoring.

### F. Thermal model-predictive control as the next substantive energy upgrade

Lee et al., *Mixed-integer model predictive control of variable-speed heat pumps*, Energy and Buildings 198 (2019), 75-83, [DOI 10.1016/j.enbuild.2019.05.060](https://doi.org/10.1016/j.enbuild.2019.05.060). Baumann et al., *Experimental validation of a state-of-the-art model predictive control approach for demand side management with a hot water heat pump*, Energy and Buildings 285 (2023), 112923, [DOI](https://doi.org/10.1016/j.enbuild.2023.112923).

These studies motivate modelling thermal state, temperature-dependent efficiency, equipment limits, demand prediction and repeated state estimation. Scheduling a fixed two-hour heat-pump task cannot establish that a home reaches 20.5 degrees or that a hot-water requirement is met.

**Not implemented in this upgrade:** thermal MPC. A credible follow-on needs measured indoor/outdoor temperature, heat-pump electricity, thermal characteristics and comfort constraints. Implement a simple calibrated resistance-capacitance model first, validate its forecasts chronologically, then replan with measured state. `fixed_starts` is groundwork for preserving commitments; it is not a complete rolling controller or state estimator.

### G. Community and learning benchmarks

Nweye et al., *CityLearn v2: Energy-flexible, resilient, occupant-centric, and carbon-aware management of grid-interactive communities* (2024), [arXiv:2405.03848](https://arxiv.org/abs/2405.03848).

CityLearn is a relevant subsequent benchmark for building/DER control under a defined simulator. Compare rule-based, MPC and learned controllers with identical observations, data splits and accounting. Report cost, comfort violations, peak load and runtime separately. No CityLearn integration or reinforcement-learning policy is included here.

McMahan et al., *Communication-Efficient Learning of Deep Networks from Decentralized Data*, AISTATS 2017, [PMLR 54](https://proceedings.mlr.press/v54/mcmahan17a.html).

Federated training becomes relevant when several households or organizations train forecasts without centralizing their raw records. First establish a useful single-site and pooled forecasting baseline. FedAvg alone is not differential privacy, secure aggregation or a defense against poisoning. No federated component was added merely to expand the technology list.

## 3. Implemented mathematical contract

For each job j and legal start s, define a binary variable x[j,s]. Exactly one start is selected:

```
sum_s x[j,s] = 1
```

A job's profile p[j,k] is in kW at offset k. With slot length dt in hours, flexible load at time t is reconstructed as:

```
L[t] = sum_(j,s where 0 <= t-s < duration[j]) p[j,t-s] * x[j,s]
L[t] + background[t] + reserve[t] <= capacity
```

The cost objective is `sum_t dt * tariff[t] * L[t]`. Background cost is reported separately but need not enter the minimization because it is fixed. Reserve is capacity headroom, not consumed energy, and is not billed as if it were demand.

The grid objective is `sum_t dt * stress[t]/100 * L[t]`. It is relative stress-weighted energy, not carbon emissions. Balanced mode combines price divided by an explicit positive reference scale with the stress index, using a declared weight. The default weight 0.56 and price scale 0.30 EUR/kWh are design parameters, not research-established optima or a current Belgian tariff.

Zero and negative tariffs are supported. Fixed starts preserve declared commitments; avoid slots are hard constraints in the advanced endpoint. The legacy avoid-hours preference remains soft for compatibility, but any relaxation is explicitly flagged. Task windows and capacity are not relaxed.

The checker independently reconstructs the selected schedule from the request. It checks exact task membership, integer starts, windows, fixed starts, avoid slots, energy and aggregate capacity. Numerical tolerances are explicit in code. The SHA-256 identifies the normalized input; it is neither a signature nor proof that measurements are authentic.

### Calibration contract

For held-out block i, calculate `score[i] = max(0, max_t(actual[i,t] - forecast[i,t]))`. With n calibration blocks and requested miscoverage alpha, select sorted score number `ceil((n+1)*(1-alpha))`, counting from one. If that rank exceeds n, reject instead of silently clipping it.

Under exchangeable calibration and future blocks, using a fixed independently trained predictor and the same forecasting procedure, this supports a marginal whole-block upper envelope. The implementation does not assert conditional coverage for each household or validity after arbitrary shifts. Appliance-profile error and unmodelled hardware behavior are not covered by a reserve calibrated only on background-load error.

## 4. Measured evidence

Authoritative numerical files are `backend/evaluation/planning_results.json` and `results.json`; both record provenance. `benchmark_planning.py` includes a reference enumerator that does not reuse production scoring or validation. Its 200 seeded problems include negative prices, multiple objectives, 15/30/60-minute units, capacity conflicts and hard avoid slots. An additional production exhaustive solver is useful for development but is not the sole correctness reference.

The recorded local run matched 110 feasible and 90 infeasible cases, with zero disagreements and maximum objective difference below 1e-15. This is strong regression evidence for these instances, not a mathematical proof for all inputs.

Scaling runs cover 8, 16, 32 and 64 jobs across 96 slots. The first two reached optimal status. The latter two returned valid incumbents at a three-second limit, with approximately 1.50% and 1.49% relative gaps. Gap is a solver objective bound, not a guaranteed percentage reduction in an electricity bill. Runtime depends on instance, machine and dependency versions; the requested solve budget is not a hard end-to-end response-time guarantee.

The synthetic reserve diagnostic uses 400 calibration blocks and 1,000 independent test blocks, with correlated errors within each block. Whole-block coverage is 928/1000 (92.8%); its Wilson interval conditional on the fitted reserve is approximately 91.0%-94.2%. Applying an unmodelled +0.2 kW shift reduces coverage to 0.4%. This deliberately visible failure demonstrates the need for drift evaluation; it is not a deployed predictor result.

The current retrieval/intent evaluation was rerun without model weights. It uses TF-IDF/SVD embeddings and the rule parser; model-based rows are marked skipped. The original August evaluation is preserved under `evaluation/historical/` and must not be presented as measurement of this revision.

The inherited 15-mission set has simplified single-deadline labels even for sentences with different device deadlines. Its exact-match score is a legacy diagnostic, not a validated semantic benchmark. In particular, the conservative rounding correction no longer agrees with a label that previously rounded 06:30 to 07:00. Those labels were not silently edited to increase the score. Build per-device, minute-accurate gold constraints before comparing intent models rigorously.

## 5. Reproduction and use

From the repository root:

```bash
npm ci
npm run lint
npx tsc --noEmit
npm test
cd backend
pip install -r requirements.txt
FLEXIGRID_EMBEDDINGS=tfidf python -m unittest discover -s tests -v
FLEXIGRID_EMBEDDINGS=tfidf python -m flexigrid.evaluate --skip-llm
python -m flexigrid.benchmark_planning
uvicorn flexigrid.api:app --host 127.0.0.1 --port 8000
```

Run `npm run dev` in a second terminal and select **Planning lab**. Load a synthetic problem or import a JSON request. Edit `jobs`, tariff, stress, background, reserves, hard avoid slots or fixed starts. Solve, inspect the status and load traces, then export request plus result. The lab requires the real Python backend and never substitutes a fabricated schedule after an error. Ollama is unnecessary for numerical planning.

API: `POST /api/planning/solve` accepts `PlanningProblem`. `POST /api/planning/calibrate` accepts matching lists of forecast and actual blocks plus alpha. A validated request file is available at `examples/planning_problem.json`. Calibration should use genuine held-out residuals, not made-up numbers copied from an example.

All times are elapsed-time slot indices. The maximum horizon is 192 slots; jobs are limited to 64. A Belgian civil day can contain 92, 96 or 100 quarter-hours around daylight-saving changes. The API does not convert local timestamps, infer missing slots or match forecast publication times. Upstream ingestion must align timestamps, units, forecast vintages, tariffs and provenance before calling it.

## 6. Deployment and research gates

This remains local-first and advisory-only. Default CORS is limited to the local frontend, but CORS is not authentication. Do not expose the API publicly without authentication, authorization, request-size and rate limits, concurrency controls, monitoring and an audited reverse proxy. The solve limit reduces solver workload per request; it does not protect against request floods or memory exhaustion.

Before physical control, add user-confirmed constraints, metered device models, electrical protection independent of this software, manufacturer interlocks, fail-safe operation, fresh-data checks and explicit consent. Do not infer real-time grid security, carbon savings, comfort or billing compliance from this scheduler.

The most valuable next research milestone is a chronological real-data forecasting and thermal-model study. Define households and holdout periods before tuning; compare seasonal-naive, gradient-boosted and suitable sequence-model forecasts; calibrate on a separate period; evaluate on untouched future periods, including deliberate shifts. Only then compare rolling MPC with a learned controller. This order makes later model and privacy claims measurable rather than decorative.

Implementation dependency reference: [SciPy `milp` documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html). Status 0 means optimal; a time-limit incumbent is not an optimality certificate. Source references were reviewed for their stated methods; no published savings percentage is transferred to this project.
