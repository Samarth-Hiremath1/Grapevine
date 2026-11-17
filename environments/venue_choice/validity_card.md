# Validity Card: `venue_choice` v1

📏 **PASS, ADVANTAGE MEASURED** — no confirmed validity failure. What one agent, or a team that does not pool, can do is measured below; read those numbers, not this line, to judge how distributed the task is.

- Tasks audited: **200**, seeds 0–199
- Grapevine: `0.2.0` · card hash: `8164b56f2ecda6ab`
- Checks: 11 pass

## Summary

| | Check | Status | Finding |
|---|---|---|---|
| 📏 | `solo_solvability` | measured | No reliable solo shortcut. Measured single-view accuracy (held-out learned probe) 32.4% [27.3%, 37.8%] against 25.0% chance and 100% with everything pooled; best explicit probe 34.9% (`scoring_rule_on_own_view[agent 0]`). Zero-information diagnostic rejected at this n (power: accuracies below 37.2% usually go unseen). |
| 📏 | `reward_hacking` | measured | No non-pooling team matches pooling (200/200) and the reward pays only for correctness. The best non-pooling team, `no_discussion_majority`, scores 36.5% [30.1%, 43.4%] against 25.0% chance; zero-information diagnostic rejected at this n. |
| ✅ | `leak` | pass | In none of 200 tasks does a view name the gold option alone or a single unit settle the task. |
| ✅ | `full_solvability` | pass | Applying the stated scoring rule to every unit gives the gold answer in 200/200 tasks. |
| ✅ | `shortcuts` | pass | No content-blind shortcut beats 25.0% chance; the best is `longest_option` at 26.4%. |
| ✅ | `name_hygiene` | pass | No option name is a substring of another, and none occurs inside an ordinary word, across 200 tasks. |
| ✅ | `minimality` | pass | All 2028 required units are load-bearing: removing any one changes the answer the scoring rule gives. |
| ✅ | `diversity` | pass | 7 distinct support patterns and 180 distinct unit templates across 200 tasks. |
| ✅ | `balance` | pass | Gold position is uniform (chi2=1.08 against a 7.81 critical value) and agents hold equal numbers of private units. |
| ✅ | `objective` | pass | All 2 conditions state both the question and the scoring rule in every prompt. |
| ✅ | `condition_diff` | pass | All 1 condition pairs have identical framing or differ only by the difference the environment declares. |
| ✅ | `scorer_fuzz` | pass | All 18 adversarial cases scored as the contract requires over 200 tasks: no false accepts, no false rejects. |
| ✅ | `seed_split` | pass | Disjoint split declared: 5000 train seeds, 500 eval seeds, 100 pilot. Overlap is refused at construction. |

## Detail

### 📏 `solo_solvability` — Solvability from one agent's view

**measured.** No reliable solo shortcut. Measured single-view accuracy (held-out learned probe) 32.4% [27.3%, 37.8%] against 25.0% chance and 100% with everything pooled; best explicit probe 34.9% (`scoring_rule_on_own_view[agent 0]`). Zero-information diagnostic rejected at this n (power: accuracies below 37.2% usually go unseen).

*Exists because of G6, P4 in `docs/audit.md`.*

```json
{
  "probes": [
    {
      "commits": 136,
      "right_when_committed": 53,
      "name": "scoring_rule_on_own_view[agent 0]",
      "n_correct": 69.75,
      "n": 200,
      "accuracy": 0.34875,
      "chance": 0.25,
      "p_value_vs_chance": 0.000227,
      "beats_chance": true,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_own_view",
      "agent_id": 0,
      "ci95": [
        0.286115,
        0.417086
      ],
      "advantage": 0.09875,
      "share_of_pooling_gain": 0.131667,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.389706,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 145,
      "right_when_committed": 42,
      "name": "scoring_rule_on_own_view[agent 1]",
      "n_correct": 58.5,
      "n": 200,
      "accuracy": 0.2925,
      "chance": 0.25,
      "p_value_vs_chance": 0.065706,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_own_view",
      "agent_id": 1,
      "ci95": [
        0.233839,
        0.358982
      ],
      "advantage": 0.0425,
      "share_of_pooling_gain": 0.056667,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.289655,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 132,
      "right_when_committed": 46,
      "name": "scoring_rule_on_own_view[agent 2]",
      "n_correct": 66.58,
      "n": 200,
      "accuracy": 0.332917,
      "chance": 0.25,
      "p_value_vs_chance": 0.001342,
      "beats_chance": true,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_own_view",
      "agent_id": 2,
      "ci95": [
        0.271295,
        0.400835
      ],
      "advantage": 0.082917,
      "share_of_pooling_gain": 0.110556,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.348485,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "mention_count_on_own_view[agent 0]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "mention_count_on_own_view",
      "agent_id": 0,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "mention_count_on_own_view[agent 1]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "mention_count_on_own_view",
      "agent_id": 1,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "mention_count_on_own_view[agent 2]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "mention_count_on_own_view",
      "agent_id": 2,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_in_my_private_units[agent 0]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_in_my_private_units",
      "agent_id": 0,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_in_my_private_units[agent 1]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_in_my_private_units",
      "agent_id": 1,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_in_my_private_units[agent 2]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_in_my_private_units",
      "agent_id": 2,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 136,
      "right_when_committed": 53,
      "name": "scoring_rule_on_my_private_units[agent 0]",
      "n_correct": 69.75,
      "n": 200,
      "accuracy": 0.34875,
      "chance": 0.25,
      "p_value_vs_chance": 0.000227,
      "beats_chance": true,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_my_private_units",
      "agent_id": 0,
      "ci95": [
        0.286115,
        0.417086
      ],
      "advantage": 0.09875,
      "share_of_pooling_gain": 0.131667,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.389706,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 145,
      "right_when_committed": 42,
      "name": "scoring_rule_on_my_private_units[agent 1]",
      "n_correct": 58.5,
      "n": 200,
      "accuracy": 0.2925,
      "chance": 0.25,
      "p_value_vs_chance": 0.065706,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_my_private_units",
      "agent_id": 1,
      "ci95": [
        0.233839,
        0.358982
      ],
      "advantage": 0.0425,
      "share_of_pooling_gain": 0.056667,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.289655,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 132,
      "right_when_committed": 46,
      "name": "scoring_rule_on_my_private_units[agent 2]",
      "n_correct": 66.58,
      "n": 200,
      "accuracy": 0.332917,
      "chance": 0.25,
      "p_value_vs_chance": 0.001342,
      "beats_chance": true,
      "ties_scored_by_expectation": true,
      "probe": "scoring_rule_on_my_private_units",
      "agent_id": 2,
      "ci95": [
        0.271295,
        0.400835
      ],
      "advantage": 0.082917,
      "share_of_pooling_gain": 0.110556,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.348485,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_not_most_named_privately[agent 0]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_not_most_named_privately",
      "agent_id": 0,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_not_most_named_privately[agent 1]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_not_most_named_privately",
      "agent_id": 1,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "named_not_most_named_privately[agent 2]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "named_not_most_named_privately",
      "agent_id": 2,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "least_shared_support[agent 0]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "least_shared_support",
      "agent_id": 0,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "least_shared_support[agent 1]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "least_shared_support",
      "agent_id": 1,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "least_shared_support[agent 2]",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true,
      "probe": "least_shared_support",
      "agent_id": 2,
      "ci95": [
        0.195082,
        0.314341
      ],
      "advantage": 0.0,
      "share_of_pooling_gain": 0.0,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": null,
      "accuracy_when_committed_lower95": null
    },
    {
      "commits": 209,
      "right_when_committed": 71,
      "name": "learned_from_view_ranks[all agents, held-out half]",
      "n_correct": 97.08,
      "n": 300,
      "accuracy": 0.323611,
      "chance": 0.25,
      "p_value_vs_chance": 0.000666,
      "beats_chance": true,
      "ties_scored_by_expectation": true,
      "probe": "learned_from_view_ranks",
      "train_tasks": 100,
      "ci95": [
        0.273188,
        0.378494
      ],
      "advantage": 0.073611,
      "share_of_pooling_gain": 0.098148,
      "never_wrong_when_committed": false,
      "accuracy_when_committed": 0.339713,
      "accuracy_when_committed_lower95": null
    }
  ],
  "chance": 0.25,
  "alpha_per_probe": 0.002632,
  "full_information_accuracy": 1.0,
  "primary_estimate": {
    "name": "learned_from_view_ranks[all agents, held-out half]",
    "accuracy": 0.323611,
    "ci95": [
      0.273188,
      0.378494
    ],
    "advantage": 0.073611,
    "share_of_pooling_gain": 0.098148,
    "n": 300
  },
  "primary_estimate_note": "The learned probe, fitted on half the batch and scored on the other half: the least optimistic single-view estimate here. The best of the explicit probes is biased upwards by being the best of nineteen.",
  "feature_twin_test": {
    "level": "feature-level only",
    "abstraction": "views compared by evidence pattern: per option (private support, private mentions, shared support, shared mentions); option names treated as exchangeable; wording, order and length ignored. Feature twins are not shown to be indistinguishable as full observations.",
    "per_agent": {
      "0": {
        "views": 200,
        "feature_twin_with_different_answer": 187,
        "feature_twins_all_same_answer": 9,
        "no_feature_twin": 4
      },
      "1": {
        "views": 200,
        "feature_twin_with_different_answer": 187,
        "feature_twins_all_same_answer": 5,
        "no_feature_twin": 8
      },
      "2": {
        "views": 200,
        "feature_twin_with_different_answer": 190,
        "feature_twins_all_same_answer": 7,
        "no_feature_twin": 3
      }
    }
  },
  "zero_information_diagnostic": {
    "label": "diagnostic only, not a validity requirement",
    "question": "does any probe beat chance at the Bonferroni-corrected alpha?",
    "rejected": true,
    "alpha_per_probe": 0.002632,
    "probes_beating_chance": [
      "scoring_rule_on_own_view[agent 0]",
      "scoring_rule_on_own_view[agent 2]",
      "scoring_rule_on_my_private_units[agent 0]",
      "scoring_rule_on_my_private_units[agent 2]",
      "learned_from_view_ranks[all agents, held-out half]"
    ],
    "minimum_detectable_accuracy": 0.372,
    "note": "Under the assumptions in docs/validity-card.md some view of an argmax-of-summed-evidence task always carries information, so this diagnostic is expected to reject once n is large enough; whether it does at this n is a statement about power."
  },
  "minimum_detectable_accuracy": 0.372,
  "rule": "fail: some probe commits to a single option on at least 20 tasks and is never wrong when it does (a reliable solo shortcut); inconclusive: fewer than 20 tasks; otherwise measured."
}
```

### 📏 `reward_hacking` — Reward earnable without pooling

**measured.** No non-pooling team matches pooling (200/200) and the reward pays only for correctness. The best non-pooling team, `no_discussion_majority`, scores 36.5% [30.1%, 43.4%] against 25.0% chance; zero-information diagnostic rejected at this n.

*Exists because of M6 in `docs/audit.md`.*

```json
{
  "reward": "the environment's own score(), as a training reward would use it",
  "genuine_pooling": {
    "n_correct": 200,
    "n": 200,
    "accuracy": 1.0,
    "mean_reward": 1.0
  },
  "policies": [
    {
      "name": "recite_without_answering",
      "n_correct": 0,
      "n": 200,
      "accuracy": 0.0,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "mean_reward": 0.0,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.0,
        0.018845
      ],
      "advantage": -0.25,
      "share_of_pooling_gain": -0.333333
    },
    {
      "name": "verbose_non_answer",
      "n_correct": 0,
      "n": 200,
      "accuracy": 0.0,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "mean_reward": 0.0,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.0,
        0.018845
      ],
      "advantage": -0.25,
      "share_of_pooling_gain": -0.333333
    },
    {
      "name": "always_first_option",
      "n_correct": 47,
      "n": 200,
      "accuracy": 0.235,
      "chance": 0.25,
      "p_value_vs_chance": 0.712995,
      "beats_chance": false,
      "mean_reward": 0.235,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.181574,
        0.298414
      ],
      "advantage": -0.015,
      "share_of_pooling_gain": -0.02
    },
    {
      "name": "random_option",
      "n_correct": 51,
      "n": 200,
      "accuracy": 0.255,
      "chance": 0.25,
      "p_value_vs_chance": 0.462094,
      "beats_chance": false,
      "mean_reward": 0.255,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.199605,
        0.319629
      ],
      "advantage": 0.005,
      "share_of_pooling_gain": 0.006667
    },
    {
      "name": "no_discussion_majority",
      "n_correct": 73,
      "n": 200,
      "accuracy": 0.365,
      "chance": 0.25,
      "p_value_vs_chance": 0.000202,
      "beats_chance": true,
      "mean_reward": 0.365,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.301405,
        0.433683
      ],
      "advantage": 0.115,
      "share_of_pooling_gain": 0.153333
    },
    {
      "name": "copy_agent_zero",
      "n_correct": 69,
      "n": 200,
      "accuracy": 0.345,
      "chance": 0.25,
      "p_value_vs_chance": 0.001699,
      "beats_chance": true,
      "mean_reward": 0.345,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.282598,
        0.413244
      ],
      "advantage": 0.095,
      "share_of_pooling_gain": 0.126667
    },
    {
      "name": "defer_to_largest_view",
      "n_correct": 70,
      "n": 200,
      "accuracy": 0.35,
      "chance": 0.25,
      "p_value_vs_chance": 0.001028,
      "beats_chance": true,
      "mean_reward": 0.35,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.287288,
        0.418365
      ],
      "advantage": 0.1,
      "share_of_pooling_gain": 0.133333
    },
    {
      "name": "share_nothing_claim_everything",
      "n_correct": 46,
      "n": 200,
      "accuracy": 0.23,
      "chance": 0.25,
      "p_value_vs_chance": 0.766831,
      "beats_chance": false,
      "mean_reward": 0.23,
      "p_value_vs_pooling": 0.0,
      "indistinguishable_from_pooling": false,
      "pays_beyond_correctness": false,
      "ci95": [
        0.177093,
        0.293083
      ],
      "advantage": -0.02,
      "share_of_pooling_gain": -0.026667
    }
  ],
  "alpha_per_probe_vs_chance": 0.00625,
  "alpha_vs_pooling": 0.05,
  "note": "Shaping terms are not included here: this environment's reward is its scorer alone. A run that adds a shaping term must re-audit with it, or the check has not seen the reward being optimised.",
  "zero_information_diagnostic": {
    "label": "diagnostic only, not a validity requirement",
    "question": "does any non-pooling team beat chance at the Bonferroni-corrected alpha?",
    "rejected": true,
    "policies_beating_chance": [
      "no_discussion_majority",
      "copy_agent_zero",
      "defer_to_largest_view"
    ],
    "minimum_detectable_accuracy": 0.362
  },
  "rule": "fail: a non-pooling team cannot be distinguished from pooling, or the reward pays beyond correctness; inconclusive: fewer than 20 tasks; otherwise measured."
}
```

### ✅ `leak` — Answer leak into a single view

**pass.** In none of 200 tasks does a view name the gold option alone or a single unit settle the task.

*Exists because of P4, G6 in `docs/audit.md`.*

```json
{
  "tasks_where_a_view_names_only_gold": 0,
  "tasks_where_one_unit_outweighs_all_rivals": 0,
  "n_tasks": 200,
  "tolerance": 0,
  "gold_string_appears_in_some_private_unit": {
    "n": 200,
    "rate": 1.0,
    "note": "Informational. A unit mentioning the gold option is normal -- it is evidence. It is only a leak when it settles the answer, which the two counts above test."
  },
  "examples": []
}
```

### ✅ `full_solvability` — Solvability with everything pooled

**pass.** Applying the stated scoring rule to every unit gives the gold answer in 200/200 tasks.

*Exists because of G5 in `docs/audit.md`.*

```json
{
  "n_correct": 200,
  "n": 200,
  "accuracy": 1.0,
  "n_tied_at_the_top": 0,
  "note": "A tie counts as unsolved: the task does not determine an answer, and a solver that guessed its way to gold would be measuring the audit's RNG.",
  "failures": []
}
```

### ✅ `shortcuts` — Content-blind shortcuts

**pass.** No content-blind shortcut beats 25.0% chance; the best is `longest_option` at 26.4%.

*Exists because of L3, I1 in `docs/audit.md`.*

```json
{
  "shortcuts": [
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "mention_count",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "fewest_mentions",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true
    },
    {
      "commits": 200,
      "right_when_committed": 47,
      "name": "first_option",
      "n_correct": 47,
      "n": 200,
      "accuracy": 0.235,
      "chance": 0.25,
      "p_value_vs_chance": 0.712995,
      "beats_chance": false,
      "ties_scored_by_expectation": true
    },
    {
      "commits": 97,
      "right_when_committed": 28,
      "name": "longest_option",
      "n_correct": 52.83,
      "n": 200,
      "accuracy": 0.264167,
      "chance": 0.25,
      "p_value_vs_chance": 0.284399,
      "beats_chance": false,
      "ties_scored_by_expectation": true
    },
    {
      "commits": 0,
      "right_when_committed": 0,
      "name": "shared_only",
      "n_correct": 50,
      "n": 200,
      "accuracy": 0.25,
      "chance": 0.25,
      "p_value_vs_chance": 1.0,
      "beats_chance": false,
      "ties_scored_by_expectation": true
    }
  ],
  "chance": 0.25,
  "alpha_per_probe": 0.01
}
```

### ✅ `name_hygiene` — Option names are distinguishable in text

**pass.** No option name is a substring of another, and none occurs inside an ordinary word, across 200 tasks.

*Exists because of G11, L5 in `docs/audit.md`.*

```json
{
  "names_that_are_substrings_of_other_names": [],
  "names_colliding_with_ordinary_words": [],
  "n_tasks_scanned": 200
}
```

### ✅ `minimality` — Minimality of the required units

**pass.** All 2028 required units are load-bearing: removing any one changes the answer the scoring rule gives.

*Exists because of G5 in `docs/audit.md`.*

```json
{
  "required_units_checked": 2028,
  "redundant_found": 0,
  "tasks_affected": 0,
  "examples": []
}
```

### ✅ `diversity` — Diversity across seeds

**pass.** 7 distinct support patterns and 180 distinct unit templates across 200 tasks.

*Exists because of L2 in `docs/audit.md`.*

```json
{
  "n_tasks": 200,
  "distinct_unit_texts": 2156,
  "distinct_unit_text_sets": 200,
  "distinct_unit_templates": 180,
  "distinct_support_patterns": 7,
  "support_patterns": [
    "(10.0, 9.0, 9.0, 9.0)",
    "(11.0, 10.0, 10.0, 10.0)",
    "(12.0, 11.0, 11.0, 11.0)",
    "(13.0, 12.0, 12.0, 12.0)",
    "(14.0, 13.0, 13.0, 13.0)",
    "(8.0, 7.0, 7.0, 7.0)",
    "(9.0, 8.0, 8.0, 8.0)"
  ],
  "mean_units_per_task": 76.0
}
```

### ✅ `balance` — Positional and per-agent balance

**pass.** Gold position is uniform (chi2=1.08 against a 7.81 critical value) and agents hold equal numbers of private units.

*Exists because of G3, L8, L9 in `docs/audit.md`.*

```json
{
  "gold_position": {
    "counts": [
      47,
      52,
      55,
      46
    ],
    "statistic": 1.08,
    "df": 3,
    "critical_05": 7.81,
    "uniform": true
  },
  "mean_private_units_per_agent": [
    24.0,
    24.0,
    24.0
  ],
  "mean_rendered_chars_per_agent": [
    2226.595,
    2222.925,
    2224.35
  ],
  "private_unit_spread": 0.0,
  "rendered_char_spread": 3.67
}
```

### ✅ `objective` — Objective stated in the prompts

**pass.** All 2 conditions state both the question and the scoring rule in every prompt.

*Exists because of I1, L1 in `docs/audit.md`.*

```json
{
  "probe_task": "venue_choice-0",
  "conditions": [
    {
      "condition": "communication",
      "description": "three organisers, each with part of the notes",
      "n_prompts": 3,
      "prompts_missing_question": 0,
      "prompts_missing_scoring_rule": 0,
      "states_objective": true
    },
    {
      "condition": "full_info",
      "description": "one organiser with every note",
      "n_prompts": 1,
      "prompts_missing_question": 0,
      "prompts_missing_scoring_rule": 0,
      "states_objective": true
    }
  ]
}
```

### ✅ `condition_diff` — Differences between conditions

**pass.** All 1 condition pairs have identical framing or differ only by the difference the environment declares.

*Exists because of L4, P6 in `docs/audit.md`.*

```json
{
  "compared": "prompt framing with the task's information removed: an arm is meant to differ in what it tells agents, so only the scaffolding is compared",
  "probe_task": "venue_choice-0",
  "n_conditions": 2,
  "n_pairs": 1,
  "verdict_counts": {
    "differs beyond its declared difference": 0,
    "undeclared difference": 0,
    "differs only by its declared difference": 1,
    "framing identical": 0
  },
  "pairs": [
    {
      "pair": [
        "communication",
        "full_info"
      ],
      "n_prompts": [
        3,
        1
      ],
      "differing_framing_lines": 2,
      "declared_expected_diff": [
        "You hold some notes; your colleagues hold others.",
        "You hold every note; there is nobody to consult."
      ],
      "sample": [
        "-You hold some notes; your colleagues hold others.",
        "+You hold every note; there is nobody to consult."
      ],
      "residual_lines_after_removing_declared_diff": 0,
      "residual_sample": [],
      "verdict": "differs only by its declared difference"
    }
  ],
  "pairs_omitted": 0
}
```

### ✅ `scorer_fuzz` — Scorer under adversarial answers

**pass.** All 18 adversarial cases scored as the contract requires over 200 tasks: no false accepts, no false rejects.

*Exists because of D1, M1 in `docs/audit.md`.*

```json
{
  "contract": "accept iff the answer, stripped of surrounding whitespace, is exactly the gold option",
  "cases": [
    {
      "case": "gold",
      "should_accept": true,
      "accepted": 200,
      "n": 200,
      "example": {
        "task_id": "venue_choice-0",
        "answer": "Brackwell"
      }
    },
    {
      "case": "gold with surrounding spaces",
      "should_accept": true,
      "accepted": 200,
      "n": 200,
      "example": {
        "task_id": "venue_choice-0",
        "answer": "  Brackwell  "
      }
    },
    {
      "case": "gold with a trailing newline",
      "should_accept": true,
      "accepted": 200,
      "n": 200,
      "example": {
        "task_id": "venue_choice-0",
        "answer": "Brackwell\n"
      }
    },
    {
      "case": "empty string",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null,
      "rationale": "resolved to option 0 in v0 (D1)"
    },
    {
      "case": "whitespace only",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "None",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "a wrong option",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "one letter",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null,
      "rationale": "resolved to option 0 in v0"
    },
    {
      "case": "gold lowercased",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "gold uppercased",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "gold with punctuation",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "gold inside prose",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null,
      "rationale": "the v0 parser returned the last option named"
    },
    {
      "case": "wrong option named last",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "two options",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "a prefix of gold",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "JSON wrapping gold",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "not an option at all",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    },
    {
      "case": "every option listed",
      "should_accept": false,
      "accepted": 0,
      "n": 200,
      "example": null
    }
  ],
  "n_false_accepts": 0,
  "n_false_rejects": 0
}
```

### ✅ `seed_split` — Declared train / eval seed split

**pass.** Disjoint split declared: 5000 train seeds, 500 eval seeds, 100 pilot. Overlap is refused at construction.

```json
{
  "train": [
    0,
    5000
  ],
  "eval": [
    10000,
    10500
  ],
  "pilot": [
    9000,
    9100
  ],
  "n_train": 5000,
  "n_eval": 500,
  "audited_seeds_in_eval": 0,
  "audited_seeds_in_train": 200
}
```

---

A `skipped` check did not run, because this environment does not provide
what it needs. That is not the same as passing, and nothing here should be
read as if it were.

Regenerate this card with:

```bash
grapevine audit venue_choice --n 200 --seed 0
```
