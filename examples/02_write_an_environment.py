"""Write a distributed-information environment and audit it.

    python examples/02_write_an_environment.py

A complete environment in one file: three agents choose a workshop venue, and
the best venue only wins once their private notes are pooled. It implements the
:class:`grapevine.Environment` protocol and passes every check on its eval
seeds. The comments say which check each design choice is there for.

"Passes" is a statistical statement. Audited over 40 disjoint seed ranges, a
clean environment like this one fails about one in twenty, always on
`shortcuts`, at the battery's 5% false-alarm rate
(``studies/battery_calibration/README.md``). Audit on the seeds you will
report, and read a lone marginal failure with that rate in mind.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import replace

from grapevine import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    SeedSplit,
    Status,
    audit,
)

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
        gold, decoy, other, spare = options
        rng.shuffle(options)  # gold is not always in the same place (`balance`)

        # r supporting facts for the gold venue per agent, varied by seed so the
        # support pattern differs across tasks (`diversity`).
        r = rng.choice([2, 3])
        support = rng.sample(SUPPORT, len(SUPPORT))
        neutral = rng.sample(NEUTRAL, len(NEUTRAL))
        counter = {"s": 0, "n": 0, "u": 0}

        def unit(venue: str, *, supports: bool) -> InfoUnit:
            pool, key = (support, "s") if supports else (neutral, "n")
            text = pool[counter[key] % len(pool)].format(v=venue) + "."
            counter[key] += 1
            counter["u"] += 1
            return InfoUnit(f"u{counter['u']:03d}", text, venue if supports else None)

        # Shared notes: the decoy leads on common ground. That is the hidden profile.
        shared = [unit(decoy, supports=True) for _ in range(2 * r - 2)]
        shared.append(unit(other, supports=True))

        # Private notes. Each agent holds r facts for the gold venue and r + 1 for
        # one other venue, so neither its whole view nor its private notes alone
        # point at the answer (`solo_solvability`, including the private-only
        # probe). Pooled, gold has 3r against the decoy's 3r - 1, so every gold
        # fact is needed (`full_solvability`, `minimality`).
        views: list[AgentView] = []
        required: list[str] = []
        for agent_id, pointer in enumerate((decoy, other, spare)):
            private = [unit(gold, supports=True) for _ in range(r)]
            required += [u.unit_id for u in private]
            private += [unit(pointer, supports=True) for _ in range(r + 1)]
            rng.shuffle(private)
            views.append(AgentView(agent_id=agent_id, private=tuple(private)))

        # Pad the shared notes so every venue is named equally often, so counting
        # names says nothing about the answer (`shortcuts`).
        named = {v: sum(u.text.count(v) for u in [*shared, *(x for w in views for x in w.private)])
                 for v in options}
        top = max(named.values())
        for venue in options:
            shared += [unit(venue, supports=False) for _ in range(top - named[venue])]
        rng.shuffle(shared)
        views = [replace(view, shared=tuple(shared)) for view in views]

        return DistributedTask(
            task_id=f"{self.name}-{seed}",
            objective=Objective(question=self.QUESTION, scoring_rule=self.RULE),
            answer_space=tuple(options),
            gold_answer=gold,
            views=tuple(views),
            required_units=tuple(required),
            metadata={"seed": seed, "decoy_option": decoy, "r": r},
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


def main() -> None:
    """Audit the environment and print its verdict and every check."""
    env = VenueChoice()
    card = audit(env, n_tasks=200, seed=env.seed_split().eval.start)
    print(f"{env.name}: {card.verdict.value}")
    for result in card.results:
        print(f"  {result.status.value:7} {result.check_id}")
    if card.verdict is not Status.PASS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
