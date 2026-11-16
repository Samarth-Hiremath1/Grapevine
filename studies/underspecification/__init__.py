"""The v0 underspecification case study.

Three agents hold the facts needed for a hiring decision between them. With no
communication they score 0.5%. Letting them talk recovers most of the loss, and
the gap that remained — which I first published as a coordination failure — was
objective underspecification: no prompt told the models what they were scored
on. With the question and scoring rule stated, the communicating teams score
100/100 and 99/100, the same as a presentation-matched single agent.

This study is why ``grapevine audit`` exists. See ``README.md`` here, and
``docs/audit.md`` at the repository root for the audit that caught it.
"""
