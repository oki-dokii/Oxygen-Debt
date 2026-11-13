# COMP10 submission handoff — 2026-11-13

**Technical status: ready to submit.** The compiler is verified; no further optimization is required to make a valid submission. Repository access and the actual event-form submission are separate administrative steps. This document does not claim that a form has been submitted or that hidden judging will pass.

## What to send

The COMP10 rules require **one GitHub repository link**:

https://github.com/oki-dokii/Oxygen-Debt

Use the default `main` branch. Judges use the last commit made before their deadline; a later push is ignored. Verified compiler code is `b637236364d9050ae5f3df6177ac76b0bc4e6578`; subsequent commits only record documentation/evidence.

Suggested form fields:

| Field | Entry |
|---|---|
| Project title | Oxygen Debt — kopt |
| Track | Compilers & Language Systems |
| Problem | COMP10 — Oxygen Debt |
| Language/runtime | Python 3.10+, standard library only; Linux x86-64 |
| Source/executable | The repository, including executable top-level `kopt`, `build.sh` and `src/` |
| Architecture/technical report | `DESIGN.md`; supporting requirements, decisions and proof documents under `docs/` |
| Benchmarks | README sample matrix, `docs/WORKFLOW.md`, `docs/FORWARDING.md` and qualification JSON reports |
| Live demo | `tests/demo.sh` with an external organizer kit |
| Verification | https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43462303399 |

Copy-paste description:

> kopt is a deterministic, offline optimizer for the Kiln intermediate representation. It uses source-derived proofs for arithmetic and bit-loop rewrites, loop transformations, memory forwarding, register reuse and scheduling, while preserving return values, traps, volatile operations and data memory. Machine parameters guide candidate selection; profiles are hints. On 500 public program/machine samples, measured cycles fall from 580,799 to 81,730. Ubuntu verification passes 97 unit tests and 738,950 generated comparisons. Fresh qualification covers larger signed sorts, overlapping matrices, unseen machines and misleading profiles; individual performance regressions are disclosed.

Team name, registered members, institution/contact fields and any declarations must use the team's actual registration details. They cannot be inferred from GitHub collaborators.

## Deliverables and readiness

| Event deliverable | Our artifact | Status |
|---|---|---|
| Source and build instructions | Repository, `src/`, `README.md`, executable `build.sh` | Ready |
| Executable/testable output | Executable Python `kopt` script plus `src/` | Ready; accepted explicitly by COMP10 |
| Architecture and implementation documentation | Seven required sections in `DESIGN.md`; PRD/TRD/SRS/decisions/research/proof documents | Ready |
| Benchmarks and test suites | Public matrix, independent VM suites, qualification reports and successful Ubuntu CI | Ready |
| Functional demonstration | Runnable `tests/demo.sh`, including sorting, merging, bit/loop wins and a trap-prefix case | Live demo ready; no prerecorded video is claimed |

The general event's binary wording does **not** require adding a native binary for this Python entry. COMP10 explicitly accepts a script named `kopt`, and forbids committing self-built binaries/build products. Do not add an `.exe`, copied starter `bench/`/`examples/`/`machines/`, or validator stamp files. The track asks for the repository link; attach a separate video/report only if the event portal requires it.

Build/run from the repository root:

```sh
./build.sh
./kopt /path/to/input.kir --machine /path/to/machine.cfg -o /tmp/output.kir
```

Optional profile:

```sh
./kopt /path/to/input.kir --machine /path/to/machine.cfg \
  --profile /path/to/input.prof -o /tmp/output.kir
```

No dependency installation or native compilation is needed. The judge supplies the input/machine files; the independent test/demo scripts use an external organizer kit.

## Checks already completed

- Top-level `build.sh`, `kopt`, `README.md` and `DESIGN.md` are tracked.
- Both entry scripts have Git mode 100755, LF endings and valid shebangs.
- The archived submission builds and runs from a different directory and passes the independent external validator.
- The optimizer writes only the requested output; representative and hold-out outputs are identical across different Python hash seeds.
- All seven required DESIGN headings are present in the required order.
- No starter benchmark/example/machine directories or build products are tracked. A scoped scan found no private-key/token markers in tracked files.
- The permitted starter parser/interpreter/timing reuse is credited. Runtime imports use the standard library and our own source.
- The local history begins November 9 and the verified release is November 13, matching the declared event window. The team should confirm its originality declaration using its actual work history.
- Ubuntu 22.04 / Python 3.10 verification passes all three groups: 97 unit tests, 500 public samples and 738,950 generated current-output comparisons. Known reference/feature skips remain separate.
- Fresh hold-out passes 5,520 equivalence checks, with 220 matrix and 160 signed-sorting oracles.

Correctness evidence is not a hidden-test guarantee. Public sample timings do not predict every hidden workload. The latest hold-out has 709 faster inputs, 4,783 ties and 28 slower inputs; sorting aggregate cycles improve 7.02%. Both worst timing losses and their replay counts are documented in `FORWARDING.md` and the regression-audit JSON.

## Finish the submission

- [x] Repository visibility is public, verified through GitHub after the user changed it during this audit.
- [ ] Verify the link opens without signing in, if public.
- [ ] Confirm the team has 1–3 registered members and the registration details are correct.
- [ ] Paste the repository link into the official submission form/channel and finish its required fields. The repository push itself is not an event submission.
- [ ] Save the confirmation/receipt and the submitted revision.
- [ ] Check the organizer's exact cutoff time/timezone. The November 9–13 event window alone does not establish a submission cutoff time; the checked COMP10 rules do not publish a dated cutoff or submission-form URL.

The user changed the repository to public during this audit; GitHub reports PUBLIC. The agent did not change access settings or submit an event form.

## Short live-demo plan

1. Show the README build/run commands and run `./build.sh`.
2. Use the external kit to validate and compare cycles for `sum_sq`, a bit-loop kernel, and a sorting/merging kernel. `sh tests/demo.sh /path/to/LLH-26/Compilers/COMP10` automates the full demonstration.
3. Show the trap-prefix case: the division trap and preceding store are preserved.
4. Briefly explain one source-level proof, machine-aware selection, and a known limitation. Keep the held-out timing regressions visible when discussing performance.

## Authoritative sources

- [Current COMP10 rules and submission requirements](https://github.com/rudra-shroff06/LLH-26/blob/main/Compilers/COMP10/RULES_AND_SUBMISSION.md)
- [Verified compiler's successful Ubuntu run](https://github.com/oki-dokii/Oxygen-Debt/actions/runs/43462303399)
- [Implementation and verification handoff](WORKFLOW.md)
- [Latest proof, results and limitations](FORWARDING.md)
