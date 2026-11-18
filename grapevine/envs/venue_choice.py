"""``venue_choice``: the supported distributed-information environment.

Three organisers choose a workshop venue; the best venue only wins once their
private notes are pooled. It is the environment from
``examples/02_write_an_environment.py``, promoted unchanged into the package so
that the evaluation and RL entry points can use it by name;
``tests/test_venue_choice.py`` keeps the two copies identical.

What its audit establishes, at 200 tasks: no confirmed validity failure, and a
measured single-view advantage -- the best possible single-agent accuracy is
29.8% against 25% chance, because, under the assumptions in
``docs/validity-card.md``, some view of any task decided by summed evidence leans
towards the answer. Its committed card is
``environments/venue_choice/validity_card.md``. It is a test bed for
coordination, not evidence that a model coordinates.

``hidden_profile_v2`` and v0 ``hidden_profile`` stay in the registry as
documented case studies of flawed environments; both fail their audits.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    SeedSplit,
)

__all__ = ["VenueChoice"]

# Names that never occur inside ordinary words (`name_hygiene`).
VENUES = (
    "Halloran", "Pemberton", "Quayside", "Vexley", "Marchetti", "Ostrander",
    "Brackwell", "Corvane", "Lindholm", "Yardley", "Thursby", "Kestrel",
)

# Many more templates than any one task uses, so tasks differ in content and
# not only in labels (`diversity`).
SUPPORT = (
    "{v} has a hall that seats every attendee without overflow rooms",
    "{v} is a ten-minute walk from the main rail station",
    "{v} includes catering for dietary needs at no extra charge",
    "{v} hosted last year's workshop with no technical failures",
    "{v} offers step-free access to every room",
    "{v} has a recording studio the speakers can use",
    "{v} quoted a price well inside the budget",
    "{v} has breakout rooms for six parallel sessions",
    "{v} guarantees reliable wifi for four hundred devices",
    "{v} has an on-site hotel with a block of rooms held for us",
    "{v} provides a dedicated events coordinator",
    "{v} allows the room to be set up the evening before",
    "{v} received the best attendee ratings in the last survey",
    "{v} has a quiet room and a prayer room on site",
    "{v} includes the projectors and microphones in the price",
    "{v} has secure storage for the poster boards",
    "{v} offers a free cancellation window of sixty days",
    "{v} has a garden that can hold the evening reception",
    "{v} is the venue our keynote speaker asked for",
    "{v} has backup power for the whole building",
    "{v} has a loading bay for the exhibitors' equipment",
    "{v} runs a shuttle from the airport at no cost",
    "{v} has live captioning equipment installed",
    "{v} is certified for the fire capacity we need",
    "{v} kept the rate fixed for three years running",
    "{v} has a creche the organisers can book",
    "{v} has recording rights included for every talk",
    "{v} has air conditioning in every session room",
    "{v} offered our society a member discount",
    "{v} has a stage large enough for the panel",
    "{v} can host the poster session in one open hall",
    "{v} has its own technicians on call during sessions",
    "{v} has bike parking for two hundred bicycles",
    "{v} offers a sustainable menu certified locally",
    "{v} is open late enough for the evening sessions",
    "{v} has a press room with separate phone lines",
    "{v} received no complaints in the last three events",
    "{v} has a lift wide enough for wheelchairs and equipment carts",
    "{v} includes coffee breaks in the day rate",
    "{v} has a signed data protection agreement with us already",
)
NEUTRAL = (
    "{v} is in the shared folder of venue brochures",
    "{v} was mentioned in last week's planning call",
    "{v} appears on the shortlist sent to the committee",
    "{v} is listed in the budget spreadsheet",
    "{v} was copied on the request for quotes",
    "{v} has a line in the travel guidance draft",
    "{v} is named in the calendar hold for the site visit",
    "{v} came up in the chair's email on Monday",
    "{v} is on the map attached to the planning notes",
    "{v} appears in the minutes of the steering meeting",
    "{v} is in the contact list for venue managers",
    "{v} was added to the comparison table last Tuesday",
    "{v} has a tab in the planning workbook",
    "{v} is named in the insurance enquiry",
    "{v} appears in the draft programme header",
    "{v} was mentioned when dates were discussed",
    "{v} has a folder in the shared drive",
    "{v} is listed in the venue directory we use",
    "{v} came up in the treasurer's update",
    "{v} is noted in the site visit schedule",
)


# Each base sentence in three settings, so a task of up to ~50 supporting facts
# never repeats one (`diversity`). No setting contains a venue name.
SETTINGS = ("", " according to last year's organisers", " as confirmed on the site visit")
SUPPORT_FACTS = tuple(base + where for base in SUPPORT for where in SETTINGS)
NEUTRAL_FACTS = tuple(base + where for base in NEUTRAL for where in SETTINGS)

#: How many times each organiser's notes name each venue. Chosen for prompt size
#: (about 28 notes per organiser); a larger K leans less, never zero.
K = 6


def _splits(total: int, cap: int) -> list[tuple[int, int, int]]:
    """Every way to split ``total`` over three organisers, each share in ``0..cap``."""
    return [(a, b, total - a - b) for a in range(cap + 1) for b in range(cap + 1)
            if 0 <= total - a - b <= cap]

class VenueChoice(Environment):
    """Three organisers choose a venue; the best one is hidden until they pool notes."""

    name = "venue_choice"
    version = "1"

    QUESTION = "Which venue should host the workshop?"
    RULE = (
        "each fact describing something a venue offers or has done counts as one "
        "supporting fact for that venue, and the venue with the most wins."
    )

    def seed_split(self) -> SeedSplit:
        """Disjoint train, eval and pilot seeds (`seed_split`)."""
        return SeedSplit(train=range(0, 5000), eval=range(10000, 10500), pilot=range(9000, 9100))

    def generate(self, seed: int) -> DistributedTask:
        """Build one task deterministically from ``seed``."""
        rng = random.Random(seed)
        options = rng.sample(VENUES, 4)
        gold = options[0]
        rng.shuffle(options)  # gold is not always in the same place (`balance`)

        # Totals: gold has t + 1 supporting facts, every other venue t. Gold wins
        # by one, so every gold fact is needed (`full_solvability`, `minimality`).
        t = rng.randint(K, 2 * K)
        totals = {v: t + (v == gold) for v in options}

        # Each venue's total is split over the three organisers uniformly at
        # random, every share in 0..K. No organiser's notes are built to point
        # anywhere in particular (`solo_solvability`).
        shares = {v: rng.choice(_splits(totals[v], K)) for v in options}

        support = rng.sample(SUPPORT_FACTS, len(SUPPORT_FACTS))
        neutral = rng.sample(NEUTRAL_FACTS, len(NEUTRAL_FACTS))
        counter = {"s": 0, "n": 0, "u": 0}

        def unit(venue: str, *, supports: bool) -> InfoUnit:
            pool, key = (support, "s") if supports else (neutral, "n")
            text = pool[counter[key] % len(pool)].format(v=venue) + "."
            counter[key] += 1
            counter["u"] += 1
            return InfoUnit(f"u{counter['u']:03d}", text, venue if supports else None)

        # Shared notes support and name every venue once: common ground favours
        # nobody (`least_shared_support`, the shared-name probes).
        shared = [unit(v, supports=True) for v in options]
        rng.shuffle(shared)

        # Private notes name every venue exactly K times -- its supporting facts
        # plus neutral mentions -- so no name count, in any block, says anything
        # (`shortcuts`, `named_not_most_named_privately`).
        views: list[AgentView] = []
        required: list[str] = []
        for agent_id in range(3):
            private: list[InfoUnit] = []
            for v in options:
                facts = [unit(v, supports=True) for _ in range(shares[v][agent_id])]
                if v == gold:
                    required += [u.unit_id for u in facts]
                private += facts
                private += [unit(v, supports=False) for _ in range(K - shares[v][agent_id])]
            rng.shuffle(private)
            views.append(AgentView(agent_id=agent_id, shared=tuple(shared), private=tuple(private)))

        return DistributedTask(
            task_id=f"{self.name}-{seed}",
            objective=Objective(question=self.QUESTION, scoring_rule=self.RULE),
            answer_space=tuple(options),
            gold_answer=gold,
            views=tuple(views),
            required_units=tuple(required),
            metadata={"seed": seed, "t": t},
        )

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """Two arms that state the objective (`objective`) and differ by one
        declared line (`condition_diff`)."""
        header = task.objective.statement() + "\n\n"
        tail = f"\n\nChoose exactly one of: {', '.join(task.answer_space)}."
        solo_marker = "You hold every note; there is nobody to consult."
        team_marker = "You hold some notes; your colleagues hold others."
        full = task.full_view()
        everything = AgentView(agent_id=0, shared=full.shared, private=full.private)
        return {
            "full_info": Condition(
                name="full_info",
                description="one organiser with every note",
                prompts=(solo_marker + "\n\n" + header + everything.render() + tail,),
                expected_diff={"communication": solo_marker},
            ),
            "communication": Condition(
                name="communication",
                description="three organisers, each with part of the notes",
                prompts=tuple(team_marker + "\n\n" + header + v.render() + tail for v in task.views),
                expected_diff={"full_info": team_marker},
            ),
        }
