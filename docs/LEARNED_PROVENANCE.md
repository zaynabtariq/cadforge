# Exact rule provenance during concurrent learning

The counterbore planner and glasses generator previously resolved a skill ID with `latest_id`, then separately called `apply` by name. A promotion between those reads could make the saved ID name a different version from the one that supplied the dimensions.

`ContinualLearning.apply_with_provenance` now returns the applied parameters, root skill ID, dependency IDs and context from a single SQLite read snapshot. Ordinary `apply` delegates to the same path. Both product callers use the combined receipt. This preserves bounded parameter checks, context matching and quarantine checks; it does not change learned coefficients or rerun discovery.

A regression test uses two actual SQLite connections and deliberately promotes a revised rule after the reader selects its version. The first receipt consistently reports the old rule and its 3.4 mm result; the next reports the new rule and its 3.6 mm result. The test also confirms that support-range rejection releases the snapshot. Its numerical executor is synthetic unit-test evidence, not a new CAD learning result.

The continual/planner/product suites pass 24 tests. An additional check applies the existing persisted tool-pocket rule and writes its actual receipt under `artifacts/learning-provenance/`. No new geometry discovery, benchmark evaluation or learned-performance improvement is claimed for this concurrency fix. Health is evaluated at the read snapshot; a later quarantine can still occur, and generated geometry must always undergo its own checks.
