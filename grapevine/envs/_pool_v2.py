"""Frozen content pool for ``hidden_profile_v2``.

**Provenance.** Every sentence in this file was drafted by a language model
(Claude Opus 5) on 2026-11-15 at Samarth Hiremath's direction, then read,
edited and frozen by hand. Nothing here was taken from another dataset, paper or
benchmark. The text is *content only*: it never carries a label. Which option a
fact supports is decided by the generator's construction, never by a model
(``CLAUDE.md`` rule 8).

**Frozen.** :data:`POOL_SHA256` is a digest over this pool, asserted by
``tests/test_hidden_profile_v2.py``. Changing a sentence changes the digest and
fails that test, because every committed run and every Validity Card describes
the tasks this pool produces. Add a new domain rather than editing an existing
sentence; if the pool must change, the environment's ``version`` changes with it.

**Two kinds of sentence, and the distinction matters.**

``support``
    Evidence about the subject. Each one counts as one supporting fact under the
    scoring rule.
``mentions``
    Names the subject while saying nothing about their merits -- scheduling,
    paperwork, logistics. Worth nothing under the scoring rule.

The generator uses ``mentions`` to make name counting uninformative. Without
them the gold option is named more often than any other, and counting names
solves the task without reading it -- which is what v0 ``hidden_profile`` did,
200 times out of 200 (``docs/audit.md`` L3). Pad carelessly and the gold option
becomes the *least*-named, which is exactly as cheap to exploit, so the
generator equalises counts rather than merely inverting them.

**No sentence leads with its subject.** In v0 every supporting fact began with
the candidate's name, so the name's position alone carried the structure. Here
the subject appears mid-sentence, and a test asserts it.

**No name hides inside a word.** No entity name is a substring of another, or of
any sentence in this pool. A test asserts both, because a name that also occurs
inside an ordinary word makes every name-matching measurement -- mention counts,
surfacing rates -- partly a count of word fragments.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

__all__ = ["DOMAINS", "POOL_SHA256", "Domain", "pool_digest"]


@dataclass(frozen=True)
class Domain:
    """One decision setting: its question, its scoring rule, and its sentences.

    A task draws entirely from one domain, so its facts are coherent together,
    and the domain varies by seed.

    Attributes:
        key: Short identifier recorded in task metadata.
        question: The question put to the team.
        scoring_rule: How the answer is determined, in words a model can act on.
        subject: What the options are, for prompt wording ("candidate").
        entities: The option names. None is a substring of another or of any
            sentence below.
        support: Sentences that are evidence, each with one ``{entity}`` slot.
        mentions: Sentences that name an entity without being evidence.
    """

    key: str
    question: str
    scoring_rule: str
    subject: str
    entities: tuple[str, ...]
    support: tuple[str, ...]
    mentions: tuple[str, ...]


_HIRING = Domain(
    key="hiring",
    question="Which candidate should the committee recommend for the role?",
    scoring_rule=(
        "each sentence describing something a candidate accomplished counts as one "
        "supporting fact for that candidate; sentences about scheduling, paperwork or "
        "logistics count for nobody; the candidate with the most supporting facts is "
        "the answer."
    ),
    subject="candidate",
    entities=(
        "Okonkwo", "Ferraro", "Lindqvist", "Nakamura", "Beaumont", "Castellanos",
        "Thornbury", "Villanueva", "Kowalczyk", "Pemberton",
    ),
    support=(
        "The incident review that halved repeat pages was run by {entity}.",
        "Two engineers now leading their own teams were trained by {entity}.",
        "The migration plan the platform team adopted was written by {entity}.",
        "Median build time fell from twelve minutes to three under {entity}.",
        "The race condition behind last winter's outage was traced by {entity}.",
        "A fifth was cut from the vendor contract in talks led by {entity}.",
        "The postmortem template now used everywhere was drafted by {entity}.",
        "Holiday on-call went uninterrupted the year it was carried by {entity}.",
        "The billing rewrite shipped without customer regressions under {entity}.",
        "The schema the analytics stack still runs on was designed by {entity}.",
        "Nine findings were closed in the security review driven by {entity}.",
        "A project that had slipped two quarters was turned round by {entity}.",
        "The service with the best uptime on the roster is owned by {entity}.",
        "Three successive intern cohorts were mentored by {entity}.",
        "The runbook that cut handover errors was compiled by {entity}.",
        "A long-standing data corruption bug was finally fixed by {entity}.",
    ),
    mentions=(
        "A room conflict moved the debrief slot booked for {entity}.",
        "The original role description was circulated to {entity}.",
        "One line of the opening's budget sheet refers to {entity}.",
        "The shortlist sent out before the loop included {entity}.",
        "A folder in the shared drive was created for {entity}.",
        "The recruiter's weekly update happens to name {entity}.",
        "Travel reimbursement paperwork is outstanding for {entity}.",
        "The agenda for the hiring sync has a line for {entity}.",
        "A calendar invitation went out late to {entity}.",
        "The coordinator's tracking sheet has a row for {entity}.",
        "A reminder that morning was addressed to {entity}.",
        "The printout handed to the panel listed {entity}.",
        "A badge was printed in advance for {entity}.",
        "The interview feedback form template went out to {entity}.",
        "One row of the scheduling spreadsheet belongs to {entity}.",
        "A parking space was reserved on the day for {entity}.",
        "The confidentiality notice was acknowledged by {entity}.",
        "An address correction was filed for {entity}.",
        "The panel's introductions began with {entity}.",
        "A follow-up call was pencilled in with {entity}.",
    ),
)

_VENDOR = Domain(
    key="vendor",
    question="Which supplier should the procurement board select?",
    scoring_rule=(
        "each sentence describing something a supplier delivered or demonstrated counts "
        "as one supporting fact for that supplier; sentences about meetings, forms or "
        "correspondence count for nobody; the supplier with the most supporting facts is "
        "the answer."
    ),
    subject="supplier",
    entities=(
        "Westmarch", "Dunhollow", "Greyfell", "Ashcombe", "Marlowbrook",
        "Harrowgate", "Stonemill", "Fenwycke", "Brightwater", "Ravensworth",
    ),
    support=(
        "Last quarter's emergency order was filled inside a day by {entity}.",
        "A twelve-month uptime guarantee has been met without exception by {entity}.",
        "The only audit with zero findings in three years was passed by {entity}.",
        "Spare parts were stocked locally at their own cost by {entity}.",
        "The integration that others quoted six weeks for was done in two by {entity}.",
        "A pricing error in our favour was reported unprompted by {entity}.",
        "Overnight support was staffed through the winter freeze by {entity}.",
        "The reference site we visited was built and is maintained by {entity}.",
        "Component failure rates were cut by a third after a redesign by {entity}.",
        "A full test harness was supplied at no charge by {entity}.",
        "Delivery windows were met every month last year by {entity}.",
        "The recall last spring was handled without disruption by {entity}.",
        "Documentation our engineers rate highest was produced by {entity}.",
        "Training for our whole team was run on site by {entity}.",
        "A hard deadline nobody else would commit to was accepted by {entity}.",
        "The compliance paperwork came back complete first time from {entity}.",
    ),
    mentions=(
        "A conference room was booked for the session with {entity}.",
        "The request for proposals was distributed to {entity}.",
        "One line of the procurement log records a call with {entity}.",
        "The non-disclosure agreement template was sent to {entity}.",
        "A shared folder was opened for correspondence with {entity}.",
        "The board's agenda allocates ten minutes to {entity}.",
        "Parking passes were arranged for the visit by {entity}.",
        "The minutes from last month note an email from {entity}.",
        "A diary clash pushed the review of {entity} to the afternoon.",
        "The supplier register has an entry for {entity}.",
        "An invoice address was confirmed with {entity}.",
        "The circulated timeline has a milestone beside {entity}.",
        "A visitor badge was issued for the walkthrough with {entity}.",
        "One row of the evaluation spreadsheet belongs to {entity}.",
        "The glossary of terms was forwarded to {entity}.",
        "A postal address was corrected on file for {entity}.",
        "The introductions at the kickoff began with {entity}.",
        "A placeholder meeting was pencilled in with {entity}.",
        "The attendance list for the briefing names {entity}.",
        "An out-of-office reply was received from {entity}.",
    ),
)

_SITE = Domain(
    key="site",
    question="Which location should the committee choose for the new facility?",
    scoring_rule=(
        "each sentence describing a measured advantage of a location counts as one "
        "supporting fact for that location; sentences about visits, scheduling or "
        "administration count for nobody; the location with the most supporting facts is "
        "the answer."
    ),
    subject="location",
    entities=(
        "Calderwick", "Pennisford", "Thrushmere", "Dunmorley", "Ellershaw",
        "Wrenfield", "Birchholt", "Oakhanger", "Stormcliff", "Yarrowdale",
    ),
    support=(
        "Grid capacity already exceeds the projected load at {entity}.",
        "Rail freight reaches the port in under two hours from {entity}.",
        "Three suitable contractors operate within the county around {entity}.",
        "Ground surveys came back clear with no remediation needed at {entity}.",
        "Planning permission for a comparable build was granted quickly at {entity}.",
        "A technical college supplies trained staff a short commute from {entity}.",
        "Flood risk was assessed as negligible over fifty years at {entity}.",
        "Fibre runs to the boundary of the plot at {entity}.",
        "Water supply tested well above the process requirement at {entity}.",
        "An existing access road takes heavy goods vehicles at {entity}.",
        "The council offered rates relief for the first five years at {entity}.",
        "Noise limits leave room for night operation at {entity}.",
        "A neighbouring tenant already runs compatible operations near {entity}.",
        "Expansion land adjoining the plot is unencumbered at {entity}.",
        "Air quality monitoring showed no exceedances over two years at {entity}.",
        "Waste handling is available within the same district as {entity}.",
    ),
    mentions=(
        "A minibus was hired for the site visit to {entity}.",
        "The original brief was copied to the office nearest {entity}.",
        "One line of the travel budget covers the trip to {entity}.",
        "An ordnance map was printed for the walk-round at {entity}.",
        "A photo folder was created for the survey of {entity}.",
        "The committee's agenda sets aside time for {entity}.",
        "Expenses for the overnight stay near {entity} are outstanding.",
        "A weather delay pushed back the inspection at {entity}.",
        "The property register has a reference number for {entity}.",
        "Contact details for the local planning officer cover {entity}.",
        "A reminder about the walk-round mentioned {entity}.",
        "The circulated schedule has a row for {entity}.",
        "A visitor permit was arranged for the survey of {entity}.",
        "One row of the comparison spreadsheet belongs to {entity}.",
        "The brief's glossary includes a note on {entity}.",
        "A postcode was corrected in the file for {entity}.",
        "The walk-round itinerary began at {entity}.",
        "A placeholder date was pencilled in for {entity}.",
        "The attendance list for the briefing names {entity}.",
        "An access code was requested for the gate at {entity}.",
    ),
)

#: Every domain, frozen. A task draws from exactly one.
DOMAINS: tuple[Domain, ...] = (_HIRING, _VENDOR, _SITE)


def pool_digest() -> str:
    """SHA-256 over every sentence, entity, question and rule in the pool."""
    payload = [
        {
            "key": domain.key,
            "question": domain.question,
            "scoring_rule": domain.scoring_rule,
            "subject": domain.subject,
            "entities": list(domain.entities),
            "support": list(domain.support),
            "mentions": list(domain.mentions),
        }
        for domain in DOMAINS
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


#: The frozen pool's digest, asserted by the test suite. If this does not match
#: :func:`pool_digest`, the pool has been edited and every committed run and
#: Validity Card built on it no longer describes the tasks the code produces.
POOL_SHA256 = "798d96e46481df23d857f769da6905ffa8eba9e01043dc3cc0595248dc3da4ee"
