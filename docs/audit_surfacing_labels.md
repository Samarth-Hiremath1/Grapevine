# Provenance of `audit_surfacing_labels.json`

**These are model labels, not human labels.** The field `human` in the JSON is a
misnomer; the file is kept byte-for-byte as committed in `1ce5f51`, and this note
records what it is.

Established on 2026-11-16 from the local session transcript in which the file
was made (Claude Code session `8c914b6a`, 2026-09-18), not from memory:

- **Who labelled.** The assistant model working in that session. It drew the
  sample, then wrote "I've labeled the 40-pair surfacing sample, judging each
  pair on whether a teammate could reconstruct the specific fact from the
  message", and scored "my labels" against the metric. No message from a person
  comes between the sample being printed and the labels being written. No person
  reviewed them afterwards, as far as the record shows.
- **What the labeller saw.** Each pair's fact and message, with the metric's
  verdict hidden per pair. It did know the sample was stratified 20
  metric-positive and 20 metric-negative. Messages were **truncated to 420
  characters** in what it was shown; a fact surfaced after that point would
  have been judged absent.
- **The sample.** 40 (fact, message) pairs from holder messages in conditions C
  and D, seed 20260918, stratified from pools of 3,430 metric-positive and 1,370
  metric-negative messages.
- **What was derived from them.** Precision 1.00 (20/20) and recall about 0.86
  for the surfacing metric (`docs/audit.md`, L5). Those are agreement rates with
  one model's judgement, not with a person's.

Every document that called these "hand labels", "human labels" or "labelled by
hand" was corrected on 2026-11-16 (`CLAUDE.md` rule 8).
