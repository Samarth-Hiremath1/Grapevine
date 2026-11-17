# Announcement draft

Not posted. For Samarth to edit and post, if at all. It contains no numbers;
the documents it points to register theirs in `docs/claims.yaml`.

---

**Grapevine v0.2: an audit for multi-agent evals, built after my own result
turned out to be wrong**

In September I reported that three LLM agents who shared every fact they needed
still made worse decisions than one agent who held all the facts. It looked like
a coordination failure. It wasn't. No prompt ever told the agents what they were
deciding or how it would be scored, and once it did, the gap closed.

Grapevine v0.2 turns the audit that caught that into a tool. `grapevine audit`
checks a distributed-information environment for the ways its premise breaks:
an answer that leaks into one agent's view, a shortcut that solves it without
reading it, an objective that never reaches the models, a scorer that can be
farmed. It runs offline, with no model and no API key, and writes a Validity
Card. The checks are tested against planted flaws they have to catch, and a
clean control they have to pass. A pass means those thirteen checks found
nothing, which is less than it sounds: an independent review found shortcuts
the audit misses, and they are listed in the docs.

Then I ran a small pre-registered eval on the environment built to pass it, and
the eval found a hole in the audit: one agent could answer from its own private
notes, and one of the three models partly did. The probe is now in the audit,
the environment fails it, and both are in the write-up, not fixed out of sight.

What is and is not in it:

- the audit and the protocol for writing environments against it;
- one bundled environment, which fails one check, and why;
- GRPO wiring through TRL that refuses to train on a flagged environment. It is
  smoke-tested only: there are no training results;
- the v0 case study, reproducible from committed runs with one command;
- the pre-registered eval, read model by model against what was registered
  before any call. It does not show that LLM teams match a single agent with
  every fact: on this environment the deciding agent could reach the answer
  alone.

Every number in the docs is re-derived from a committed run by
`grapevine verify-claims`, and fails CI if it drifts.

Repository: https://github.com/Samarth-Hiremath1/Grapevine
