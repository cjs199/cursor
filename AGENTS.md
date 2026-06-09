# AGENTS.md

## Repository overview

`main` is a minimal stub (`README.md` only). Runnable code lives on feature branches:

| Branch | Type | Entry point |
|--------|------|-------------|
| `cursor/btc-purchase-plan-4cf5` | Python 3 CLI (stdlib only) | `python3 plan.py [--budget N] [--json]` |
| `cursor/expr-eval-a320` | Single-file Java | `javac ExprEval.java && java ExprEval` |
| Other `cursor/*` branches | Markdown docs only | N/A |

## Cursor Cloud specific instructions

### Runtimes (pre-installed on the VM)

- **Python 3.12** — no virtualenv or pip deps required for the BTC plan CLI.
- **OpenJDK 21** (`java` / `javac`) — for `ExprEval.java`.

### Working on a feature branch

Check out the branch you need, or use a worktree to avoid switching `main`:

```bash
git worktree add /tmp/btc-plan origin/cursor/btc-purchase-plan-4cf5
cd /tmp/btc-plan && python3 plan.py
```

### Lint / test / build

There is no shared lint config, test suite, or build system on `main`. Per-branch checks:

- **BTC plan (`plan.py`)**: `python3 plan.py` and `python3 plan.py --json` — both should exit 0 and print a purchase plan.
- **Expr eval (`ExprEval.java`)**: `javac ExprEval.java && java ExprEval` — runs 20 built-in test cases plus one stdin expression.

### Secrets

None required. The BTC plan uses bundled JSON under `data/`; no API keys or network calls at runtime.
