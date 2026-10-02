# Independent validation and operational hardening

Review date: 2 October 2026. Builds on revision `f271f745fd6c089aca58bd396c52ce949fcd3ca5`.


## Changes

The follow-up review preserves the integrated MILP, Planning lab and whole-block
calibration architecture instead of adding a second competing solver API.
The published task/start checker now reconstructs window, horizon, fixed-start,
not-before and blocked-slot constraints without calling the solver's candidate
builder. This prevents a candidate-generation defect from being repeated by
both the solver and its supposed independent checker.

`not_before_slot` is an elapsed-time lower bound for new decisions. An explicitly
fixed task can remain before that bound, so replanning does not silently move
already-committed work. This is a scheduling primitive, not a closed-loop MPC
implementation or a civil-time conversion service.

The numerical HTTP solve endpoint has per-process admission control and a
separate validation endpoint. HTTP 429 indicates a busy solver, 422 an invalid
or infeasible request, and 503 a solver stop without an acceptable incumbent.
The process-local gate does not impose a fleet-wide quota, cover every endpoint,
provide authentication or certify physical safety.

The browser's labelled positive-price fixture now uses energy-weighted cost and
the same fixed-scale balanced scoring convention as the Python planner. Its
validator checks task membership, immutable task properties and exact-duration
windows before constructing load, and does not round load before capacity
checking. The fixture is still not the advanced solver.

Sentence-transformer initialization is cached-only with remote code disabled,
matching the optional offline fallback contract. A unit test verifies the
constructor arguments without downloading a model. This does not turn optional
live Elia requests into offline operations. See the
[official constructor documentation](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).

Additional tests deliberately corrupt the solver candidate builder, exercise
past-slot and committed-start behavior, validate untrusted schedules through the
HTTP endpoint, check resource-gate release after errors, and independently
enumerate signed-price scheduling cases. Their purpose is implementation
verification, not a model-quality or household-savings claim.
