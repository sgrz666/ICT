# Test Infrastructure & Specification: dsh-core

> 2026-10-31 状态修正：This is a research prototype test design, not production sign-off or proof of equivalence to native dsh. See README.md for concrete capability gaps.

## 1. Test Philosophy

The `dsh-core` test infrastructure adheres to an **opaque-box, contract-driven verification philosophy**. Rather than relying on internal implementation trivia or tautological mocks, all tests are designed against formal specifications, state transitions, and observable side-effects outlined in `PROJECT.md` and upstream DeepSeek Harness architecture standards:

1. **Behavioral Fidelity Over Structural Mocking**:
   - Tests assert on verifiable physical outcomes: exact file mutations on disk, process return codes and captured standard output streams, append-only JSONL event records, and KV-cache friendly compaction summaries.
   - No tautological assertions (e.g. `assert True`, checking mocks without exercising business logic).
2. **Zero Upstream Cross-Contamination**:
   - All tests execute strictly within ephemeral, isolated workspaces created via `tmp_path` fixtures.
   - Upstream `deep-agent/deepseek-harness/` is strictly treated as read-only reference data and is never modified.
3. **Windows Native Conformance**:
   - Subprocess management is verified against native Windows semantics (handling `taskkill /F /T`, CMD/PowerShell encoding, file locks, path separators).
   - Zero requirement for Linux container daemons or administrator DACL elevation.
4. **Progressive Testability & Decoupled Execution**:
   - Each subsystem (`file`, `sandbox`, `session`, `memory`) is covered by unit tests that can execute independently, culminating in end-to-end integration flows.

---

## 2. 4-Tier Test Architecture

The verification suite is structured into four progressive tiers:

```
+-------------------------------------------------------------------------------+
|                       Tier 4: Real-World Scenarios                            |
| - Student code execution & self-correction loop                               |
| - Educational experiment parameter editing (Optics & Circuit)                 |
| - Long-turn dialogue with multi-stage 8-section checkpointing                 |
+-------------------------------------------------------------------------------+
                                        ^
                                        |
+-------------------------------------------------------------------------------+
|                     Tier 3: Cross-Feature Combinations                        |
| - Turn/Step state machine driving Tool Execution & Result logging             |
| - File Manager write/edit gated by Sandbox Policy & Path Containment          |
| - Session Event Log stream driving Memory Token Meter & Compaction            |
+-------------------------------------------------------------------------------+
                                        ^
                                        |
+-------------------------------------------------------------------------------+
|                      Tier 2: Boundary & Corner Cases                          |
| - Path escape attempts (traversal, absolute paths, alternate drives)          |
| - Subprocess timeouts & hung child process tree termination                   |
| - Empty files, large binary/text buffers, non-UTF8 bytes                      |
| - Middle-omission pruning thresholds, token boundary overruns                 |
+-------------------------------------------------------------------------------+
                                        ^
                                        |
+-------------------------------------------------------------------------------+
|                         Tier 1: Feature Coverage                              |
| - File Subsystem: Read, atomic write, diff generation, str_replace, search    |
| - Sandbox Subsystem: ProcessRunner, policy enforcement, Windows compat, Mock  |
| - Session Subsystem: Event sourcing v4, SurfaceManager, JSONL persistence     |
| - Memory Subsystem: TokenMeter heuristic, OutputPruner, 8-section compaction  |
+-------------------------------------------------------------------------------+
```

### 2.1 Tier 1: Feature Coverage (>=5 test cases per feature)

Each subsystem provides at least 5 dedicated unit test cases per core feature:

1. **File Subsystem (`dsh_core.file`)**:
   - `FileManager.read`: Text reading, line-number windowing (`start_line`, `end_line`), offset limit.
   - `FileManager.write`: Clean file creation, atomic staging, overwrite flag enforcement.
   - `FileManager.list_dir`: Directory recursive/non-recursive listing, metadata reporting.
   - `StrReplaceEditor`: Exact unique string substitution, single-occurrence enforcement, ambiguous match rejection.
   - `ContextualDiff`: Unified 3-line hunk generation, added/removed line markers.
   - `FileSearch`: Grep regex search across files, glob path pattern filtering.

2. **Sandbox Subsystem (`dsh_core.sandbox`)**:
   - `ProcessSandbox`: Execution of commands, exit code capture, stdout/stderr separation.
   - `SandboxPolicy`: Enforcement of `READ_ONLY`, `WORKSPACE_WRITE`, and `DANGER_FULL_ACCESS`.
   - `WindowsCompat`: UTF-8 console encoding setup, shell dispatch (`pwsh`/`cmd.exe`).
   - `MockSandbox`: Deterministic execution simulation, mocked exit codes and outputs.
   - `PathContainment`: Canonical boundary verification preventing directory escape.

3. **Session Subsystem (`dsh_core.session`)**:
   - `SessionEvent`: Format Version 4 compliance, monotonic sequence numbering, timestamping.
   - `SurfaceManager`: Sequential `append` operation tracking active model-visible events.
   - `SurfaceManager`: Range `replace` operation shadowing older event intervals.
   - `JsonlPersistence`: Atomic append-only serialization to disk, file lock safety.
   - `JsonlPersistence`: Resume session from disk, verifying state reconstruction.
   - `ReactLoopState`: Turn and Step lifecycle state machine (`turn/start`, `step/start`, `step/end`, `turn/end`).

4. **Memory Subsystem (`dsh_core.memory`)**:
   - `TokenMeter`: 4-character density estimation heuristic + exact model usage accumulation.
   - `OutputPruner`: Bounded middle-omission character truncation (`[... N chars omitted ...]`).
   - `CompactionEngine`: Context pressure evaluation and threshold trigger calculation.
   - `8-Section Summarizer`: Formatting structured Markdown checkpoints with required headers.
   - `In-Place Replacement`: Updating session surface with compaction summary while preserving underlying log.

---

### 2.2 Tier 2: Boundary & Corner Cases

Defensive validation against extreme inputs, malicious operations, and resource starvation:

1. **Path Boundary Escapes**:
   - Attempts to access `..` relative paths traversing outside `workspace_root`.
   - Absolute paths targeting Windows system directories (`C:\Windows`, `C:\Program Files`).
   - Malformed paths with null bytes or alternate drive letters.
2. **Subprocess Resilience & Process Tree Cleanup**:
   - Commands spawning persistent child background processes (e.g. `ping -t 127.0.0.1`, long sleep).
   - Timeout triggers verifying that `taskkill /F /T` terminates both the parent runner and all spawned descendants.
3. **Data Integrity & Non-UTF8 Handling**:
   - Reading and writing empty files (0 bytes).
   - Reading files with mixed line endings (`\r\n` vs `\n`).
   - Graceful fallback when reading binary or invalid UTF-8 files.
4. **Token & Compaction Extremes**:
   - Compaction triggered when context limit is immediately exceeded on step 0.
   - Compaction requested when active surface has zero tool results or zero compressible turns.
   - Pruning tool results smaller than the threshold (ensuring no spurious modification).

---

### 2.3 Tier 3: Cross-Feature Combinations

Validating interface contracts between interacting subsystems:

1. **File Operations ↔ Sandbox Path Containment**:
   - `FileManager` writes rejected when attempting to save outside workspace under `WORKSPACE_WRITE` policy.
   - `ProcessSandbox` working directory validated against workspace root boundary.
2. **Turn/Step Loop ↔ Tool Dispatch & Result Logging**:
   - Simulated agent step executing a file edit tool, emitting `tool/call` and causal `tool/result` with `sourceEventSeqs`.
   - Tool execution failure properly captured as an error result event rather than crashing the loop.
3. **Session Event Log ↔ Memory Compaction**:
   - As multi-turn dialogue expands, `TokenMeter` signals threshold overrun.
   - `CompactionEngine` extracts compressible span, synthesizes 8-section checkpoint, and emits `replace` surface operation.
   - `Session.derive_messages()` verified to return only the checkpoint and recent turns, while `Session.log` retains full fidelity.

---

### 2.4 Tier 4: Real-World Scenarios

End-to-end simulations mirroring realistic educational AI agent workloads:

1. **Student Code Execution & Self-Correction**:
   - Student submits a buggy Python script with a syntax or runtime error.
   - Agent runs script in Sandbox, captures stderr traceback.
   - Agent applies `StrReplaceEditor` to fix the bug, re-runs in Sandbox, and captures exit code 0.
2. **Educational Experiment Parameter Tuning (Optics & Circuit)**:
   - Agent reads experiment configuration JSON/YAML.
   - Updates lens focal length or resistor value using diff-guided editing.
   - Verifies configuration integrity and diff generation.
3. **Long-Turn Dialogue & Context Checkpointing**:
   - Simulation of an extended tutoring dialogue (20+ turns).
   - Two consecutive compaction cycles triggered.
   - Verifies that KV-cache friendly prefixes and 8-section summaries retain critical educational constraints.

---

## 3. Test Suite Organization

```
deep-agent/dsh-core/tests/
├── README.md                  # Test suite overview, run instructions, and results baseline
├── conftest.py                # Pytest fixtures: temp workspaces, mock LLMs, event builders
├── test_file_management.py    # Tier 1 & 2 tests for FileManager, Diff, StrReplace, Search
├── test_sandbox_execution.py  # Tier 1 & 2 tests for ProcessSandbox, Policies, Windows runner
├── test_session_dialogue.py   # Tier 1 & 2 tests for Session, Surface, JSONL persistence, Loop
├── test_memory_context.py     # Tier 1 & 2 tests for TokenMeter, Pruner, CompactionEngine
└── test_integration.py        # Tier 3 & 4 tests for cross-subsystem and real-world workflows
```

---

## 4. Execution Commands

From the workspace root or `deep-agent/dsh-core`:

```powershell
# Run the complete test suite with verbose output
python -m pytest deep-agent/dsh-core/tests -v

# Run individual subsystem tests
python -m pytest deep-agent/dsh-core/tests/test_file_management.py -v
python -m pytest deep-agent/dsh-core/tests/test_sandbox_execution.py -v
python -m pytest deep-agent/dsh-core/tests/test_session_dialogue.py -v
python -m pytest deep-agent/dsh-core/tests/test_memory_context.py -v
python -m pytest deep-agent/dsh-core/tests/test_integration.py -v

# Run with test coverage report
python -m pytest deep-agent/dsh-core/tests --cov=dsh_core --cov-report=term-missing
```
