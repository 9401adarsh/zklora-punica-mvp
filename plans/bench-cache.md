### Bench Cached Setup Mode (Opt-In, Fingerprinted, Auto-Rebuild)

### Summary
Add a **bench-only cached setup mode** that reuses proof setup artifacts across timestamped benchmark runs, with explicit opt-in and safe invalidation.  
Chosen decisions:
- Scope: **Bench only**
- Activation: **Opt-in CLI flag**
- Miss policy: **Auto-build and persist**
- Safety: **Fingerprint + rebuild on mismatch**
- Visibility: **Expose cache hit/miss in benchmark summaries**

### Implementation Changes
- **Bench CLI + wiring**
  - Add `--setup-cache-root <path>` to `bench/phase4b_bounded_peft.py`.
  - Default behavior unchanged when flag is omitted (current per-run `runtime_artifacts/proof_setup` behavior).
  - When flag is set, pass cache-root through benchmark case execution into adapter construction.

- **Adapter cache behavior**
  - Extend adapter construction to accept optional setup cache root (bench path only; no server behavior change unless explicitly used).
  - Resolve setup dir with a fingerprinted path using:
    - cache schema version
    - backend (`cpu|gpu`)
    - `ezkl.__version__`
    - base model id
    - adapter id
    - module id
  - On each job:
    - If required setup files exist and fingerprint metadata matches: **cache hit**, skip setup.
    - If missing/incompatible/incomplete: **cache miss**, rebuild setup artifacts into cache path.
  - Add a per-setup-dir lock to avoid concurrent rebuild races from multiple worker threads.

- **Metrics/reporting for bench outputs**
  - Emit per-proof cache metadata into worker artifact refs (e.g., hit/miss + cache key).
  - Aggregate in benchmark case summary:
    - `setup_cache.enabled`
    - `setup_cache.hits`
    - `setup_cache.misses`
    - `setup_cache.hit_rate`
  - Keep existing timing/status fields unchanged.
  - Update benchmark markdown summary to include cache stats.

- **Docs**
  - Update `bench/README.md` with:
    - new `--setup-cache-root` usage examples
    - cache behavior (fingerprint, auto-rebuild, hit/miss reporting)
    - note that cache reuse is cross-run only when cache root is stable.

### Public Interface Changes
- New benchmark CLI option:
  - `bench/phase4b_bounded_peft.py --setup-cache-root <path>`
- Benchmark summary JSON/MD gains cache reporting fields (additive).
- No change to MVP API endpoints/payloads.

### Test Plan
- **Backward compatibility**
  - Run existing bench tests with no cache flag; ensure behavior remains unchanged.
- **Cache mode functional**
  - First run with `--setup-cache-root`: records miss/build.
  - Second run with same params/root: records hit/reuse and lower setup time.
- **Invalidation**
  - Change a fingerprint input (backend or ezkl version mock); verify miss + rebuild.
- **Concurrency safety**
  - Multi-thread bench case with shared cache root; verify no corruption and deterministic terminal statuses.
- **Summary reporting**
  - Validate new `setup_cache` fields in per-case `summary.json` and top-level summary markdown.

### Assumptions / Defaults
- Default remains **off** unless `--setup-cache-root` is provided.
- Auto-rebuild is always used on miss/mismatch in this bench mode.
- Fingerprint metadata is authoritative for compatibility checks.
- Server runtime behavior stays unchanged unless explicitly wired to use cache root in a future follow-up.
