"""Pretty-print a rollout transcript with private-fact surfacing highlighted.

Renders each episode in a JSONL transcript as a readable conversation using
``rich``: agent messages are shown in round order, and the required private
facts are listed color-coded by whether -- and in which round -- they surfaced.
Surfaced facts are green (with the round they first appeared), facts that never
surfaced are red. This makes the core failure mode visible at a glance: a team
that answered wrong will typically show several red, never-surfaced facts.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from grapevine.rewards.reward import compute_surfacing, fact_surfaced
from grapevine.rollout.engine import Episode, load_transcript

_AGENT_COLORS = ["cyan", "magenta", "yellow", "green", "blue", "bright_red"]


def _agent_color(agent_id: int) -> str:
    return _AGENT_COLORS[agent_id % len(_AGENT_COLORS)]


def render_episode(episode: Episode, console: Console, threshold: float = 0.7) -> None:
    """Render a single episode to ``console``."""
    report = compute_surfacing(episode, threshold)

    header = Text()
    header.append(f"{episode.task_id}", style="bold")
    header.append(f"  [{episode.family}]\n", style="dim")
    header.append("Q: ", style="bold")
    header.append(episode.question + "\n")
    verdict_style = "bold green" if episode.correct else "bold red"
    header.append("Team answer: ", style="bold")
    header.append(f"{episode.team_answer}", style=verdict_style)
    header.append("   Gold: ", style="bold")
    header.append(f"{episode.gold_answer}\n", style="green")
    header.append("Surfacing rate: ", style="bold")
    rate_style = "green" if report.surfacing_rate == 1.0 else "yellow"
    header.append(f"{report.surfacing_rate * 100:.0f}%", style=rate_style)
    console.print(Panel(header, title="Episode", border_style=verdict_style))

    # Conversation, with any surfaced required fact underlined in the message.
    for message in episode.messages:
        color = _agent_color(message.agent_id)
        label = f"Agent {message.agent_id} · r{message.round_no} · {message.role}"
        body = Text(message.content)
        for fact in episode.required_private_facts:
            if fact_surfaced(fact, message.content, threshold):
                body.stylize("underline")  # message contains a surfaced fact
                break
        console.print(Panel(body, title=label, border_style=color, title_align="left"))

    # Required private facts, color-coded by whether/when they surfaced.
    facts_text = Text()
    for fact in episode.required_private_facts:
        round_no = report.first_round.get(fact)
        if round_no is None:
            facts_text.append("✗ never surfaced  ", style="bold red")
            facts_text.append(fact + "\n", style="red")
        else:
            facts_text.append(f"✓ round {round_no}  ", style="bold green")
            facts_text.append(fact + "\n", style="green")
    if episode.required_private_facts:
        console.print(Panel(facts_text, title="Required private facts", border_style="dim"))
    console.print()


def view_transcript(path: str | Path, threshold: float = 0.7) -> None:
    """Load a JSONL transcript and pretty-print every episode."""
    episodes = [Episode.from_dict(d) for d in load_transcript(path)]
    console = Console()
    if not episodes:
        console.print("[yellow]No episodes found in transcript.[/yellow]")
        return
    n_correct = sum(1 for e in episodes if e.correct)
    for episode in episodes:
        render_episode(episode, console, threshold)
    console.print(
        f"[bold]{len(episodes)} episode(s), {n_correct} correct "
        f"({n_correct / len(episodes) * 100:.0f}%).[/bold]"
    )
