# External review: Grapevine v0.2 (branch `v0.2`, HEAD `2df6516`)

## 1. Verdict

The bookkeeping is unusually good. Every registered number re-derives from committed data. The pre-registration was committed before the first call and has only been appended to since. The committed runs regenerate byte-for-byte. The GRPO work is described honestly as wiring only. The scientific claims are weaker than that bookkeeping suggests, for two reasons.

First, the headline reading of the v2 eval, "`gpt-5.6-luna` replicates the v0 finding", depends on a pre-registered reading whose stated premise is "an environment with no known shortcut". That premise is false, by the authors' own A2 finding and by further shortcuts listed below. The reading also treats "the 95% interval includes 0" as if it showed equivalence.

Second, the audit battery is calibrated only against all-or-nothing defects that its own author planted. Simple probes outside its list show that `hidden_profile_v2`, the "clean" control and the example environment can all be solved from one agent's view well above chance. A decisive answer leak in 1 task in 5 passes every relevant check. I would ship the tool as "a checklist of thirteen known failure modes". I would not ship it as a calibrated validity checker, and I would not call any v2 result a replication.

## 2. Findings, most severe first

[V] = verified by running something; the command or probe is given. [J] = judgement from reading code or docs.

### B1. Blocking: "replicates the v0 finding" is not supported [V+J]

**What is wrong.** Three separate problems with the claim.

- **The reading's premise is false.** `README.md:121` and `studies/v2_eval/README.md:48` apply the replication reading from prereg §10. That reading says: "The v0 finding replicates on an environment with no known shortcut". Since A2, v2 has a known single-agent shortcut. Its own card fails `solo_solvability` at 200/200.
- **The shortcut is open to the agent that decides.** In the `communication` arm, agent 0 gives the team's answer. Applying the stated rule to agent 0's own private facts gives gold on all 100 eval tasks (`h1_investigation.md`: 300/300 agents). So a team answering correctly does not show that information was pooled.
- **Pooling was never measured.** The v2 eval did not measure whether facts were shared. v0 did ("shared every required fact in 200 of 200").

I ran an exploratory proxy using the repository's own `fact_surfaced` at threshold 0.7. In `gpt-5.6-luna`, communication, objective stated, 17 of the 95 correct episodes did not surface every gold fact held by agents 1 and 2. With margin 1, the stated rule needs all of those facts to reach gold. This is not conclusive: the authors measured the metric's recall at about 0.86 on v0. But it is the analysis a replication claim needs, and nobody ran it.

**The statistics are not an equivalence test.** The H3 contrast is +3.0, 95% [−2.0, +8.0], Bonferroni [−4.0, +11.0]. An interval that includes 0 is not evidence of a match. The data are consistent with a gap of up to 8 points (11 after Bonferroni), beyond the ±5 margin. The prereg's "inconclusive" reading ("includes 0 but is wider than ±10") does not say which interval it means. The Bonferroni interval, which the other §10 readings use, does extend past +10.

**Fix.** Replace "replicates" with "no gap detected; equivalence within ±5 not established". State next to the number that agent 0 can reach gold from its own private facts. Add a surfacing analysis, labelled exploratory.

### M1. Major: the battery misses single-view shortcuts in v2, the control and the example [V]

I used probes of the same kind as the battery's own (file `probes.py` / `venue.py`, logic in the Appendix):

| Environment, seeds | Probe on one agent's view | Correct |
|---|---|---|
| `hidden_profile_v2`, 0–199 | pick among options named in my private notes, excluding the most-named (names only, no content) | **600/600** |
| same | pick uniformly among options named in my private notes | 298/600 (49.7%) |
| same | pick uniformly among options with the least shared support | 393/600 (65.5%) |
| same, the `full_info` prompt | most-named option in the "Facts only you know" block | **200/200** |
| `hidden_profile_v2`, eval 10000–10099 | the same four probes | 300/300, 150/300, 184/300, 100/100 |
| `control` (the clean fixture), eval 1000–1199 | least shared support / any private support / anything but the shared leader | 308/600, 298/600, 189/600 (p=2e-4) |
| `venue_choice` (`examples/02`), eval seeds | the same three | 299/600, 290/600, 205/600 (p=3e-7) |

Chance is 25% throughout.

What this shows:

- **v2's A1 fix only flipped the signal.** The fix made the name count in an agent's private notes point the wrong way, which makes it non-monotonic rather than uninformative. The docstring of `fewest_mentions` (`solvers.py:143-155`) warns against exactly this.
- **Gold has no shared support by construction.** In every family here, the gold option never appears in the shared facts, so "pick the option the common ground ignores" beats chance.
- **The `full_info` arm carries a layout cue.** "Presentation-matched" puts all gold support in a block labelled "Facts only you know". That is a candidate explanation for `gpt-6-luna`'s +0.0 objective effect at 99/99, and for `gpt-4o-mini` scoring 86/100 *without* the rule. The pre-registered "rule recoverable from the facts" reading was applied without considering it.
- **"Clean" depends on the probe list.** The control and the example "pass every check" only because these probes are not in the battery. The control was rewritten after A2 so that it passes the new probe (`docs/audit.md` A2, "The clean control did not distribute private support either"). Calibration that redefines its own clean reference after each miss is circular.

**Fix.** Add elimination and least-shared-support probes, and a names-only probe on the private block. Audit the `full_info` prompt's sections separately. Say plainly that a pass means "these thirteen probes found nothing", and stop calling the result calibrated validity. Get fixtures from someone other than the person who wrote the checks.

### M2. Major: a partial leak passes leak, solo_solvability and reward_hacking [V]

`check_leak` (`checks.py:196-198`) tests the *share of tasks that leak* against chance *accuracy* (0.25) with a one-sided binomial test. That is a category error: a leak in any task is a defect, whatever chance accuracy is.

I wrapped `ControlEnv` so that the decisive-leak flag is applied to a random fraction of seeds (`partial_leak.py`), then audited 200 tasks:

| Leak fraction | Tasks with a decisive unit | Verdict | leak | solo_solvability |
|---|---|---|---|---|
| 0.1 | 23/200 | warn | pass | pass |
| 0.2 | 43/200 | warn | pass | pass |
| 0.3 | 69/200 | fail | fail | fail |

At 43/200, agent 0 can settle more than one task in five alone, and the card's summary still says the leak counts are "both at or below chance".

The leak check also runs its two probes at uncorrected α=0.05 (lines 197-198). That contradicts `docs/audit-battery.md`, which says beats-chance families are Bonferroni-corrected within each check.

**Fix.** Fail on any decisive unit, or on a low tolerance. Add dose-response fixtures at 5%, 10% and 20%.

### M3. Major: `minimality` misreports its count by a factor of over 200 [V]

`checks.py:545` caps `redundant` at 10 entries. The summary at line 565 then reports `len(redundant)` as the total. On the `redundant_required` fixture the card says "10 of 3654 units … are not" required, but recomputing directly gives **2127** redundant units (`mini.py`). The calibration test checks only the status (`warn`), so it passes. Fix: count separately from the sample list, and test the count.

### M4. Major: `gpt-6-luna`'s H3 result is read loosely [V]

**The prediction failed and the README does not say so.** Prereg §2 predicts H3 "within ±5 points with its 95% interval including 0". For `gpt-6-luna` it is +7.0, 95% [+2.0, +13.0]: both conditions fail, so the prediction failed. README line 124 says only that it "falls between the pre-registered readings".

**Half the gap is failures to answer.** There are 9 discordant pairs: 8 where only `full_info` was correct and 1 where only `communication` was. In 4 of the 8 (`hidden_profile_v2-10019`, `-10024`, `-10072`, `-10090`), the communication answer was truncated and unparsed. Counted as incorrect, which the prereg requires, that is correct. But neither README mentions it, and the "gap" reading requires a truncation audit.

**"Exactly 0" is an artefact.** The "Bonferroni lower bound exactly 0" comes from the percentile bootstrap: the 0.36% tail is estimated from about 36 of 10,000 resamples. With bootstrap seed 1 the bound is −0.01; with the pre-registered seed it is 0.00. An exact McNemar test gives two-sided p=0.039, which is not significant at 0.05/7.

**Fix.** Report "H3 prediction not met; no pre-registered reading applies", give the truncation split, and drop "exactly 0".

### M5. Major: who produced the labels contradicts itself (rule 8) [V by grep]

Several documents describe the surfacing labels as made by hand:

- `README.md:159-160`: "40 hand labels"
- `studies/underspecification/README.md:153`: "model-free hand labels"
- `docs/methodology.md:141`
- `docs/audit.md:112-113`: "labelled by hand"
- `docs/assumptions.md:323`: "one person produced them"

Against that, the header of `docs/claims.yaml` says "who produced the labels is an open question (docs/PROGRESS.md, Step 8)". `PROGRESS.md` has no Step 8 entry. I cannot tell who labelled them. Resolve it, then either keep "hand" or relabel them as model labels everywhere.

### m1. Minor: "run in CI" when CI has never run [V by reading]

`docs/rl.md:32-35` marks the smoke, isolation, LoRA and self-play tests as "**run in CI**". `PROGRESS.md` Step 7 says "nothing has run on GitHub, because nothing is pushed". `ci.yml:3-7` triggers only on pushes to `main` and pull requests into `main`. In a table titled "What has and has not been run", that is a provenance error. Write "run locally (date); configured for CI".

### m2. Minor: process gaps against CLAUDE.md [V]

- The last three commits (`143dbff`, `1b686cc`, `2df6516`) do not update `docs/PROGRESS.md`. The Mechanics rule requires it.
- The prereg header still reads "Status: pre-registered, not run".

### m3. Minor: verify-claims is narrower than its wording [V]

A mutation test on a `git archive` copy confirmed that registered numbers are caught: 67/69 after two edits. But some claims only check part of the sentence:

- `readme.v0.one-pattern` renders "All 200 tasks share one support pattern" from `n_tasks`. It never checks `distinct_support_patterns == 1`.
- `v2.h1.luna.max-6` checks one cell, not "at most" across four.
- Many templates are short substrings, such as "and {correct} against".

From the installed wheel, `grapevine verify-claims` crashes with a raw `FileNotFoundError: 'docs/claims.yaml'` because the default path is relative to the working directory.

### m4. Minor: the frozen digest includes prompts that were never sent [V]

600 of the 1,600 frozen "opening prompts" for the primary run were never sent in that form:

- agents 1 and 2's round-one turns, which always see agent 0's message;
- the aggregator's decision prompt with an empty discussion.

I checked separately that all 3,600 prompts that genuinely open an episode (pilot plus primary) match the design byte-for-byte (`sent.py`, `sent2.py`). CI does not run that sent-versus-frozen check; it should.

### m5. Minor: the false-fail study [V]

The two "clean" environments fail on the same seed ranges with the same counts: 1200, `first_option` 66/200; 6000, `fewest_mentions` 77/200. Their generators make the same sequence of random calls, so 80 audits amount to about 40 independent ones. Per M1, both environments also have real single-view shortcuts, so "every failure here is a false alarm" is only true relative to the battery.

### m6. Minor: unregistered numbers that disagree [V]

- "Fail roughly one clean environment in four" (`audit-battery.md:170`) and "near 23%" (`checks.py:109`) disagree with the repository's own simulation, which gives 0.1925 (the test docstring says "one in five").
- "The tests record the collateral" (`audit-battery.md:77`): no test does (grep for "collateral" in `tests/` finds nothing).

### m7. Minor: battery mechanics [J]

- `objective` and `condition_diff` inspect only `ctx.tasks[0]` (`checks.py:747`, `892`).
- `balance` silently passes beyond df=20.
- `balance` counts units but cannot see direction: in v2, agent 0, the aggregator, always holds the decoy-pointer mentions (`hidden_profile_v2.py:349`).
- Cards say "at or below chance" for 31.5% when they mean "not significantly above".
- The `private_support_all_gold` fixture flips one flag but also changes the `rounds` distribution and the decoy's support. It is not a single defect.

### m8. Minor: an unexplained result was not audited (rule 11) [V, exploratory]

`gpt-4o-mini` scored 62/100 in `full_info` with the objective stated and 86/100 without it. With the rule stated and `gold_support=6`, it chose the decoy 23 times in 52. Without the rule, hiring tasks scored 34/34. This is attributed to "capability" without any audit; the M1 layout cue is an untested alternative.

### n1. Nits [V]

- The `grapevine/audit/__init__.py` docstring example says `('shortcuts',)`. It now returns `('solo_solvability', 'shortcuts', 'objective')`, and the example appears in the API docs.
- `docs/index.md:38,41` links to `blob/main/...` files that exist only on `v0.2`.
- README links and the README image break on PyPI. This is already acknowledged in `PROGRESS.md`.
- README tells users to run `python examples/...` after `uv sync` without activating the environment, and gives "Requires Python 3.11" next to "3.11–3.13".
- `tests/test_v2_eval.py:63,180` use instance-method class fixtures, which pytest has deprecated and will remove in version 10.
- `audit/__init__.py` mentions an "`--allow-flagged` list"; the flag is a boolean.

## 3. Checked and found sound

- **Tests and tooling.** `uv run pytest -q`: 382 passed in 44.8 s, with 2 deprecation warnings. Ruff and mypy are clean (56 files). `tests/test_rl_training.py` with the `[rl]` extra: 6 passed.
- **Claims and generated files.** `grapevine verify-claims`: 69/69. These `--check` scripts report unchanged: `studies.v2_eval.freeze`, `h1_investigation`, `report`, `battery_calibration.false_fail` and `underspecification.freeze_prompts`.
- **Regeneration.** `studies.underspecification.reproduce`, run on a `git archive` copy, produces byte-identical tables, CSV and v0 card. `grapevine audit hidden_profile_v2 --n 200 --seed 0` exits 2 and reproduces the committed card byte-for-byte.
- **Pre-registration order.** The prereg was committed at 2026-11-15 23:39:59 PST. The first pilot directory is stamped 07:40:17Z, which is 23:40:17 PST, 18 seconds later. The prereg diff since then appends to §11 only. `design.py` and `analyze.py` are unchanged since the prereg commit. `results.json` is unchanged since `5c203b1`.
- **Episode integrity.** Gold, decoy and option order in all 2,160 committed v2 episodes match the generator.
- **Guards.** Seed disjointness is enforced in code. Synthetic runs are refused by the analysis and by verify-claims. The RL smoke manifest says `synthetic: true, reportable: false`. GRPO is consistently described as "smoke-tested; no training results", and the zero-gradient smoke run is disclosed.
- **Spend.** $3.0655 cumulative, under the $10 cap.
- **Runtime claim.** "Under a second" holds: the audit takes 0.18 s in-process on 200 v2 tasks.

## 4. Not checked

- Anything that needs an API call: model behaviour, provider invoices, and whether pilot accuracies were really left unread.
- The citations in `docs/related-work.md` and the HiddenBench figures (no network fetch).
- GitHub Actions and the release workflow as executed, and `mkdocs build --strict`.
- The v0 study beyond regeneration and verify-claims. `REPORT.md` and `docs/results.md` were not read in full.
- The untracked `launch/` drafts (`announcement.md`, `pr-v0.2.md`, `release-checklist.md`).
- Whether the surfacing labels are correct.

## Appendix: the probes, so the numbers above can be re-run (rule 1)

These are throwaway scripts outside the repository. Each needs only `grapevine.protocol.support_total`, `grapevine.audit.solvers.count_mentions`, the environments, and a `random.Random`. For each agent view `v` of task `t`, with `opts = t.answer_space`:

- **Named, not most-named:** let `pn[o] = count_mentions(join(private texts), o)`. Choose among `{o : 0 < pn[o] < max(pn)}`.
- **Least shared support:** let `sh = support_total(v.shared, opts)`. Choose uniformly among the arg-min options.
- **Anything but the shared leader:** choose uniformly among options with `sh[o] != max(sh)`.
- **`full_info` cue:** arg-max of `pn` over `t.full_view().private`.
- **Partial leak:** use `ControlEnv(leak_decisive_unit=True)` when `Random(seed*31+7).random() < frac`, otherwise `ControlEnv()`, and audit 200 tasks from seed 0.
- **Statistics:** p-values come from `binomial_tail_p`. McNemar is the exact two-sided binomial test on the discordant pairs. Bootstrap-seed sensitivity re-runs `bootstrap_ci(diffs, 10000, seed, 0.05/7)`.

Reviewer (independent pass, no prior context)
