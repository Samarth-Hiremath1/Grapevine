# Related work

Every entry was fetched from its source on 2026-11-16, and the details below are
what that fetch showed. Nothing here is vendored: papers are cited by arXiv
identifier and version. An entry that could not be checked says **UNVERIFIED**.

## The phenomenon

**Hidden profiles in human groups.** Stasser, G., & Titus, W. (1985). Pooling of
unshared information in group decision making. *Journal of Personality and
Social Psychology*, 48(6), 1467–1478. **UNVERIFIED**: no copy was consulted.
The paradigm every environment here is built on: shared evidence favours one
option, the evidence for the right one is split across members, and groups pick
the wrong one.

**HiddenBench.** Li, Y., Naito, A., & Shirado, H. *Systematic Failures in
Collective Reasoning under Distributed Information in Multi-Agent LLMs.*
arXiv:2505.11556, v4 (13 May 2026). Proceedings of the 43rd International
Conference on Machine Learning (ICML 2026), PMLR 306 — read from the PDF's first
page; the arXiv listing says "Accepted to ICML 2026". The PDF's SHA-256 is
`f8aa0dc11b590f398c58b9ab396c05c18f12c8d1fe6a842d6b6c78bb1ebc3842`, the same
file checked on 2026-09-19 (`docs/decisions.md`).

A 65-task benchmark on the Hidden Profile paradigm. Its abstract reports 30.1%
accuracy for multi-agent LLMs under distributed information against 80.7% for
single agents given complete information. Re-checked against the PDF for this
release:

- the discussion system prompt (Appendix A.4) begins with the task
  description, and the published example description states what is decided,
  the options, that exactly one is correct, and the payoff for choosing it;
- tasks resolve by elimination: every other option should clash with at least
  one fact;
- the default accuracy is the proportion of agents choosing correctly, with a
  majority rule as a secondary measure.

Those are the three reasons its numbers and this repository's are not
comparable (`docs/results.md`). The arXiv HTML rendering of the same version
encodes the prompt templates and truncates them, so it cannot be used to check
the first point; the PDF can.

Grapevine reproduces the hidden-profile effect; it claims no novelty for it.

## Auditing benchmarks

**ABC.** Zhu, Y., Jin, T., Pruksachatkun, Y., *et al.* (25 authors).
*Establishing Best Practices for Building Rigorous Agentic Benchmarks.*
arXiv:2507.02825, v5 (7 August 2025). No venue listed. Proposes the Agentic
Benchmark Checklist, guidelines for task setup and reward design, after finding
flaws that misstate agent performance by up to 100% in relative terms; applied
to CVE-Bench, it reduced overestimation by 33%.

**BenchGuard.** Tu, X., Wang, T., Lu, Y. (M.), Huang, K., Qu, Y., & Mostafavi,
S. *Who Guards the Benchmarks? Automated Auditing of LLM Agent Benchmarks.*
arXiv:2604.24955, v2 (2 October 2026), described as the COLM 2026 camera-ready.
Uses frontier LLMs to cross-check a benchmark's artefacts and reports finding
real issues in two scientific benchmarks.

How Grapevine differs from both: it is narrow. It audits one property —
whether a distributed-information task actually requires pooling — with
programmatic solvers and planted-flaw calibration, offline and without a
model. ABC is a checklist for agentic benchmarks in general; BenchGuard uses
models as auditors. The three are complementary, and nothing here was compared
against either.

## Training

**GRPO.** Shao, Z., Wang, P., Zhu, Q., Xu, R., Song, J., *et al.* (11 authors).
*DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language
Models.* arXiv:2402.03300, v3 (27 April 2024). Introduces Group Relative
Policy Optimization, a variant of PPO. `grapevine.rl` uses GRPO through TRL and
contributes no algorithm.

**TRL.** von Werra, L., Belkada, Y., Tunstall, L., Beeching, E., Thrush, T.,
Lambert, N., Huang, S., Rasul, K., Gallouédec, Q., Dirhoussi, A., Villanova del
Moral, A., & Paniego Blanco, S. *TRL: Transformers Reinforcement Learning.*
Software, first released 2020-03-27, https://github.com/huggingface/trl — as
given in the repository's `CITATION.cff`. Grapevine pins TRL 1.18
(`docs/v0.2-plan.md`).
