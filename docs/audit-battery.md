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
| `leak` | The gold answer, or a statistic sufficient for it, sits in one agent's view | P4, G6 |
| `solo_solvability` | Some solver on a single view beats chance, so pooling is optional | G6, P4, **A1** |
| `full_solvability` | The stated scoring rule does not reach the answer even with everything pooled | G5 |
| `shortcuts` | A content-blind solver — most-named, least-named, first option, longest option, shared facts only — beats chance | L3, I1 |
| `name_hygiene` | An option name is a substring of another, or hides inside an ordinary word, so name matching counts word fragments | G11, L5 |
| `minimality` | A unit the environment calls required is not load-bearing | G5 |
| `diversity` | Every seed is the same puzzle rearranged | L2 |
| `balance` | Gold position is skewed, or one agent is systematically better informed | G3, L8, L9 |
| `objective` | A condition's prompts never state the question or the scoring rule | I1, L1 |
| `condition_diff` | Two arms differ in framing beyond the manipulation under test | L4, P6 |
| `scorer_fuzz` | The scorer accepts answers it should reject, or rejects ones it should accept | D1, M1 |
| `reward_hacking` | A degenerate team earns the reward without pooling, or the reward pays for something other than being right | M6 |
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

So `tests/fixtures/flawed_envs/` holds one environment per planted defect, each
being the clean control with exactly one flag flipped — a decisive unit that
leaks the answer, a gold option named more often than any other, private units
that all point at the answer, conditions that never state the objective, a
baseline that changes framing as well as information, over-declared required
units, the v0 parser's lenient matching, gold always listed first, a reward
bonus for verbosity, and a generator that emits one task forever. CI requires
the check named for each defect to fire, and the control to pass all thirteen.

A planted defect usually trips more than one check — a leak really does also
make a task solo-solvable. The requirement is that the responsible check
catches it; the tests record the collateral rather than tolerating it silently.

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

`grapevine/envs/hidden_profile_v2.py` is the bundled environment that passes all
thirteen, with each design choice traced to the finding it answers; its card is
`environments/hidden_profile_v2/validity_card.md`.
`tests/fixtures/flawed_envs/__init__.py` is a smaller worked example, and
`grapevine/envs/adapters.py` shows how an environment that predates the protocol
is wrapped rather than rewritten.

## Several probes, one threshold

A check that runs several probes corrects for it. Five shortcut probes at an
uncorrected alpha of 0.05 fail roughly one clean environment in four, and an
auditor that cries wolf that often is one people learn to ignore. The
"beats chance" families are Bonferroni-corrected within each check and the
threshold used is recorded on the card as `alpha_per_probe`. The
"indistinguishable from pooling" test is *not* corrected, because there a
smaller alpha would make a degenerate policy more likely to be called a match
for real pooling, which is the conclusion to reach least lightly.

`docs/audit.md` S3 applied the same correction to the study's four paired
comparisons. `tests/test_audit.py` demonstrates the uncorrected error rate by
simulation rather than asserting it from theory.
