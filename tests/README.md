# Testing FiveFury

The same tests run against a source checkout and an installed ABI3 wheel.
No game installation or private fixture is required for the default suite.

## Setup

```powershell
python -m pip install ".[test]"
python -m pytest -q
```

For an editable checkout, use `python -m pip install -e ".[test]"` and rebuild
the extension after C++ changes. There is no Python fallback for missing native code.

## Suites

| Suite | Purpose | Requirements |
| --- | --- | --- |
| `unit` | Current API, binary invariants, synthetic assets, failures and ownership | Test dependencies only |
| `integration` | Independent game files, fixture corpus and runtime format evidence | Explicitly configured external inputs |
| `abi` | Load the exact built extension in Python 3.11 | `FIVEFURY_ABI_TEST_PYTHON` |
| `performance` | Repeatable measurements of supported hot paths | Test dependencies; game benchmarks also require integration selection |

```powershell
python -m pytest --suite unit -q
python -m pytest --suite unit --suite abi -q
python -m pytest --suite integration -k native_reader -q
python -m pytest --suite performance --benchmark-disable -q
python -m pytest --suite performance --benchmark-json build/performance.json
```

The summary lists every collected suite before selection. Deselected cases are
**not passed tests**. `--suite all` explicitly requests everything, including
external data and game benchmarks. Use it only on a fully configured machine.

A selected test cannot silently skip. Missing prerequisites fail, unknown markers
are errors, and empty parameter sets fail collection. Platform contracts use
`requires_platform`; they are selected only on the named OS.

## External Inputs

Configure these variables outside the repository; never commit machine paths,
game binaries or private samples:

| Variable | Value |
| --- | --- |
| `FIVEFURY_REFERENCE_DIR` | Corpus root; default is the checkout's `references/` |
| `FIVEFURY_GTA5_LEGACY_PATH` | Legacy installation root |
| `FIVEFURY_GTA5_ENHANCED_PATH` | Enhanced installation root |
| `FIVEFURY_ABI_TEST_PYTHON` | Python 3.11 executable |

Some historical regression cases expose a more specific `FIVEFURY_TEST_*`
override beside their test. Their failure message identifies the missing file.
Game-pair tests run each configured edition; an invalid configured path is an
error rather than an empty parameter set.

Reference tests retain comparisons against independent retail data. Generated
fixtures cover general behaviors such as roundtrips, edited animation channels,
archive precedence and malformed buffers, but do not replace that external evidence.

## Wheel Validation

```powershell
python -m build --wheel
python tools/test_wheel.py dist/fivefury-VERSION-cp311-abi3-win_amd64.whl --suite unit -q
```

The runner installs the wheel in a temporary target, copies only tests and their
fixtures to a separate directory, runs outside the checkout with isolated Python,
and asserts where FiveFury was imported from. Child interpreters and source audits
also inspect that installation. Test dependencies must already exist in the
selected interpreter; `--python` selects a different interpreter.

Use `--junitxml reports/unit.xml` to keep a report outside the temporary directory.
External corpora must use an absolute configured path when testing a wheel.

CI builds once with Python 3.14 headers and tests that wheel on Windows with
Python 3.11, 3.12, 3.13 and 3.14. It includes the explicit ABI-floor test and
performance-case smoke tests, without downloading game data or publishing a release.

## Adding Tests

### Dense YCD Authoring

```powershell
python tools/benchmark_ycd.py --actors 8 --bones 64
```

This deterministic workload spans 262.833 seconds, 7,886 frames and six sections.
Three quarters of the bone tracks are dynamic; the rest are constant. Actors share
a source motion to bound fixture setup cost, but all their tracks are constructed,
serialized and validated independently. The output reports encoding, binary
read-back, precision validation, final serialization and peak working-set memory.
Precision time includes the binary roundtrip; do not sum overlapping stage times.

Use `--package-root` to compare an isolated installed version with the checkout,
using the same interpreter and workload. This measures warm, in-memory authoring,
not asset discovery, cold conversion or total application startup. Keep timing
assertions out of correctness tests.

### Test Contracts

- Import the current API directly; missing APIs must fail.
- Prefer `tmp_path`, typed objects and small deterministic inputs.
- Keep independent binary assertions where a reader/writer roundtrip could share a bug.
- Mark external and performance cases explicitly, even in an otherwise unit-only module.
- Do not use `skip`, `skipif`, `importorskip`, compatibility lookup helpers or optional assertions.
- Check observable behavior instead of artificial delays or relative wall-clock thresholds.
- Compare timing results only on controlled hardware with matching inputs; do not impose
  fixed timing thresholds on shared CI runners.
- Keep every test source and distributable synthetic fixture in Git.

Passing these suites does not establish in-game behavior for every possible asset.
External validation and runtime testing remain separate evidence.
