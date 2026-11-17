# The audit battery

`grapevine audit <env>` runs thirteen model-free checks over a batch of generated
tasks and emits a Validity Card. It needs no API key, no network and no GPU, and
it takes under a second on 200 tasks.

```bash
grapevine audit hidden_profile                  # Markdown card to stdout
grapevine audit hidden_profile --out out/       # validity_card.json + .md
grapevine audit hidden_profile --only leak,shortcuts
grapevine envs                                  # what can be audited
```

It exits `0` when no check failed and `2` when one did, so it works as a CI
gate. A warning does not fail the command: a limitation that is reported and
understood is not the same as an environment that does not measure what it
claims.

## Why these thirteen

Each check exists because of a specific mistake, and all but one because of a
mistake in this repository. Every `CheckResult` carries the `docs/audit.md`
finding it came from, so the battery cannot drift into checking things nobody
has ever got wrong.

| Check | What it catches | Came from |
|---|---|---|
| `leak` | In any task, a view names only the gold option or holds a unit that outweighs every rival. Zero tolerance | P4, G6, **M2** |
| `solo_solvability` | A reliable solo shortcut: one agent's view lets a probe commit to the answer and never be wrong (`fail`); otherwise the single-view advantage, measured with an interval and the audit's power (`measured`) | G6, P4, **A1**, **A2**, **M1** |
| `full_solvability` | The stated scoring rule does not reach the answer even with everything pooled | G5 |
| `shortcuts` | A content-blind solver — most-named, least-named, first option, longest option, shared facts only — beats chance | L3, I1 |
| `name_hygiene` | An option name is a substring of another, or hides inside an ordinary word, so name matching counts word fragments | G11, L5 |
| `minimality` | A unit the environment calls required is not load-bearing | G5 |
| `diversity` | Every seed is the same puzzle rearranged | L2 |
| `balance` | Gold position is skewed, or one agent is systematically better informed | G3, L8, L9 |
| `objective` | A condition's prompts never state the question or the scoring rule | I1, L1 |
| `condition_diff` | Two arms differ in framing beyond the manipulation under test | L4, P6 |
| `scorer_fuzz` | The scorer accepts answers it should reject, or rejects ones it should accept | D1, M1 |
| `reward_hacking` | A non-pooling team earns as much as pooling, or the reward pays for something other than being right (`fail`); otherwise what a non-pooling team earns (`measured`) | M6 |
| `seed_split` | No declared train/eval split, so an RL run can train on the seeds it reports | — |

## The four statuses

The statuses are deliberately four, not two.

- **`pass`** — the check ran and found nothing.
- **`warn`** — the check ran and found a real limitation, reported with its
  numbers. The environment still measures something, but narrower than it may
  appear.
- **`fail`** — the check ran and found that the environment does not measure
  what it claims. A coordination result from it would not mean what it says.
- **`skipped`** — the check could not run, because the environment does not
  provide what it needs. **Not** the same as passing, and never presented as
  such. A card made entirely of skipped checks reads "NOT ESTABLISHED".

A card's verdict is the worst status among the checks that ran.

## How it is calibrated

A battery nobody has shown a known-bad input is a battery that passes
everything, and an environment auditor that passes everything is worse than
none: it launders a flawed environment as a checked one.

The limit of this, stated first: it shows the battery catches the flaws its
author thought to plant (see "Known gaps" below). Measured over disjoint seed
ranges, it misses none of them: every negative control, `hidden_profile_v2` and
v0 `hidden_profile` is caught on 10 of 10 ranges
(`studies/battery_calibration/README.md`).

So `tests/fixtures/flawed_envs/` holds one environment per planted defect, each
being the clean control with exactly one flag flipped — a decisive unit that
leaks the answer, a gold option named more often than any other, private units
that all point at the answer, conditions that never state the objective, a
baseline that changes framing as well as information, over-declared required
units, the v0 parser's lenient matching, gold always listed first, a reward
bonus for verbosity, and a generator that emits one task forever. Added after
the v2 eval and the external review: the control's two earlier layouts, each a
real shortcut (A2, M1); gold left out of the shared facts; agent 0 always
holding gold's largest share; and a decisive leak in 5%, 10% and 20% of tasks.
CI requires the check named for each defect to report its declared status, on
several disjoint seed ranges for the review's findings; the graded leak
(`gold_share_bias`) is declared `measured`, not `fail`. It requires the control
to pass every other check and to report `measured`, never `fail`, on the two
that measure, and that the zero-information diagnostic, when it rejects, does so
only through probes that read the support the task is about.

A planted defect usually trips more than one check — a leak really does also
make a task solo-solvable. The requirement is that the responsible check
catches it. The other checks a defect trips are not asserted by the tests.

On top of that, the battery is required to rediscover this repository's own v0
findings, by finding number: L3 (name counting solves 200/200), I1 (the
objective never reached the models), L2 (one puzzle in 200 arrangements), L9
(agent 0 holds one more fact), L4 (the baseline arm differed in framing),
plus the checks that should still pass — G3, G5, and the scorer that D1 fixed.
`split_evidence`, which leaked its answer for real before any of this existed,
is a real-world positive control: the leak check reproduces the hand count of
100 out of 100.

## What it found that the hand audit did not

`solo_solvability` reports that in v0 `hidden_profile`, every private fact
supports the correct option and the distractors name nobody, so an agent
asking only "whose name is in my secret notes?" is right in 200 of 200 tasks
with no pooling at all.

The hand audit tested solo solvability by applying the task's own scoring rule
to one view. That genuinely gives the decoy, so it read 0/200 and was recorded
as clean. It was right about the rule and wrong about the space of things a
model might do. Written up as A1 in `docs/audit.md`.

It changes no reported number — condition B scored 0.5%, so the models did not
take the shortcut — but it changes the interpretation: B's near-zero accuracy
is a fact about these models, not a property of the task.

## What a model found that the battery did not

The first pre-registered eval on `hidden_profile_v2` found a gap in the battery
itself. v2 answered A1 by equalising name counts, so the name-counting probe
passed. But every private *supporting* fact still favoured gold, and nothing in
the battery applied the scoring rule to one agent's private facts alone. That
solver is right for 300 of 300 agents on the eval tasks, and `gpt-4o-mini`,
with the objective unstated, voted gold from its own view 125 times in 300.

The probe is now in `solo_solvability`, with a planted-flaw fixture only it
catches. v2 fails it and keeps failing it, because its generator is frozen.
Written up as A2 in `docs/audit.md`; the investigation is
`studies/v2_eval/h1_investigation.md`.

The lesson is about calibration: a battery is calibrated against the flaws its
authors thought to plant. This gap was in the fixtures too, because the clean
control had the same layout as v2.

## What it does not do

- **It does not run a model.** Every check interrogates the task construction,
  the prompts and the scorer. A validity problem should be findable before any
  tokens are spent, but a problem that only appears in behaviour will not be
  found here.
- **It does not see shaping terms it is not given.** `reward_hacking` scores
  degenerate policies with the environment's own scorer. A training run that
  adds a shaping term has to re-audit with it, or the check has not seen the
  reward being optimised.
- **It does not check prompts an environment does not describe.** `objective`
  and `condition_diff` need `Environment.conditions()`. Without it they report
  `skipped`, which is why `skipped` is a visible status and not folded into
  `pass`.
- **It only sees the opening prompts.** Later turns embed a transcript that does
  not exist before a rollout.
- **Thirteen checks are not all the checks.** Passing means thirteen known
  failure modes were looked for and not found.

## Why a pass is a bound

`solo_solvability` used to fail whenever any probe beat chance. For an
environment whose answer is the unique argmax of evidence summed over what each
agent sees, with the answer uniformly distributed over the options, that
requirement cannot be met: some single view always carries information about
the answer, and the Bayes-optimal guess from it beats chance. The assumptions,
the argument, and where it does not apply are in
[`docs/validity-card.md`](validity-card.md#why-zero-information-is-a-diagnostic-not-a-requirement).

Under the old rule, the same environment passed or failed depending on whether
200 tasks happened to be enough to see a lean that is always there. So the
check now separates three cases:

- **A reliable solo shortcut fails.** A probe that commits to one option on at
  least 20 tasks and is never wrong. v0 `hidden_profile` and
  `hidden_profile_v2` fail this way; so do both earlier control layouts.
- **Anything less is measured.** The card reports single-agent accuracy from a
  held-out learned probe, chance, the advantage, a 95% interval, the share of the
  pooling gain, and the audit's power. The status is `measured` whether or not
  the zero-information test rejects at this n.
- **Under 20 tasks is inconclusive.**

The strict zero-information test is still run and reported, labelled as a
diagnostic. Every card states the minimum detectable accuracy: at 200 tasks, a
per-agent probe usually misses a true single-view accuracy below 37.2%.

The clean control and the example show the difference. Their exact
Bayes-optimal single-view accuracy is 29.8% against 25% chance. Over 40 seed
ranges each, the zero-information diagnostic rejects on 17 for the control and
`solo_solvability` reports `measured` on all 40
(`studies/battery_calibration/README.md`). The twin test certifies, for most
views, that an indistinguishable instance with a different answer exists.

`reward_hacking` follows the same rule: a non-pooling team that beats chance is
a measured advantage, and fails only when it cannot be told apart from pooling
or the reward pays for something other than being right.

## Known gaps

Found by the external review (`docs/review-v0.2.md`) and re-derived in
`studies/v2_eval/review_followup.md`.

- **Fixed: the names-only shortcut (M1).** `solo_solvability` now includes
  `named_not_most_named_privately`, `least_shared_support`, and a learned probe
  that fits any rule over within-view ranks of private and shared support and
  name counts on half the batch and tests it on the other half. The two layouts
  that had the shortcut are kept as negative controls (`legacy_pointer_support`,
  `legacy_gold_only_private_support`), and fail on every seed range tested.
- **Fixed: partial leaks (M2).** `leak` fails on a single leaking task. Planted
  leaks in 5%, 10% and 20% of tasks fail on every seed range tested.
- **Open: probes are still a list.** The learned probe covers any rule over its
  four rank channels, but a shortcut in a channel it does not see -- sentence
  templates, unit order, text length -- is missed until someone adds it.
- **Open: the layout cue in conditions.** Nothing audits what a condition
  prompt's sections give away. The rebuilt control and example do not have the
  cue (gold's support is not all private), but `hidden_profile_v2` does.
- **Open: calibration is still self-written.** The planted flaws, the adversarial
  fixtures and the clean control were all written by the person who wrote the
  checks. A fixture set from someone else would be a real test.
- **Smaller mechanics.** `objective` and `condition_diff` inspect only the first
  task. `balance` counts units per agent but not which way they point.
  `reward_hacking`'s team policies still break ties at random.

## Writing an auditable environment

Implement `Environment.generate(seed) -> DistributedTask`. That is the minimum;
everything else has a default, and checks that need more say `skipped`.

The protocol asks for a little more than "a prompt and a gold string", and each
part is what makes a check possible:

- **Information units**, not one blob per agent, so `minimality` can remove one
  and ask whether the answer changes.
- **An objective** with the question *and* the scoring rule, so `objective` can
  check both reach the prompts verbatim.
- **A programmatic scorer**, so `scorer_fuzz` can probe it and so a reward is
  verifiable without a model.
- **`conditions()`**, optional, to enable `objective` and `condition_diff`.
- **`seed_split()`**, optional, so an RL user cannot train on eval seeds.

`grapevine/envs/hidden_profile_v2.py` is the bundled environment, with each
design choice traced to the finding it answers; its card is
`environments/hidden_profile_v2/validity_card.md`. It passed all thirteen checks
when it was built, and fails `solo_solvability` since the probe added after its
eval (A2, below).
`tests/fixtures/flawed_envs/__init__.py` is a smaller worked example, and
`grapevine/envs/adapters.py` shows how an environment that predates the protocol
is wrapped rather than rewritten.

## Several probes, one threshold

A check that runs several probes corrects for it. Five shortcut probes at an
uncorrected alpha of 0.05 fail roughly one clean environment in five (the
simulation in `tests/test_audit.py`), and an
auditor that cries wolf that often is one people learn to ignore. The
"beats chance" families are Bonferroni-corrected within each check and the
threshold used is recorded on the card as `alpha_per_probe`. The
"indistinguishable from pooling" test is *not* corrected, because there a
smaller alpha would make a degenerate policy more likely to be called a match
for real pooling, which is the conclusion to reach least lightly.

`docs/audit.md` S3 applied the same correction to the study's four paired
comparisons. `tests/test_audit.py` demonstrates the uncorrected error rate by
simulation rather than asserting it from theory.

**Ties are scored by their expected value.** A solver facing a k-way tie that
includes the gold option scores 1/k instead of drawing one at random, and the
p-value comes from the exact null distribution of that score. A fully tied view
then contributes exactly chance with no variance, so a solver with no
information cannot fail an environment by drawing lucky tie-breaks. Before this
change, that noise failed clean environments about one audit in twenty, on
`shortcuts`. (`reward_hacking`'s team policies still break ties at random.)

**What that leaves.** The correction is within a check, not across checks or
repeated audits, and a check can still be wrong at its nominal rate. Measured
over 40 disjoint seed ranges (`studies/battery_calibration/README.md`), each
clean environment's verdict is `measured` on 38 and differs on 2, both ordinary
type I errors on the randomised gold position: `shortcuts` fails once, because
`first_option` was right in 66 of 200 tasks, and `balance` warns once, on a
chi-square of 9.64 against 7.81. Neither is the measured advantage.
