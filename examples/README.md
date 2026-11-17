# Examples

Each one runs offline, needs no API key and no model, and is executed by the
test suite (`tests/test_examples.py`), so none of them can silently rot.

| File | What it shows |
|---|---|
| [`01_audit_an_environment.py`](01_audit_an_environment.py) | Audit two bundled environments and read their Validity Cards. |
| [`02_write_an_environment.py`](02_write_an_environment.py) | A complete environment in one file, written against the protocol, that passes every check on its eval seeds. |
| [`03_score_and_gate_a_reward.py`](03_score_and_gate_a_reward.py) | What one agent sees, how an answer is scored, and the audit gate refusing a flagged environment and a hackable reward. |

```bash
python examples/02_write_an_environment.py
```
