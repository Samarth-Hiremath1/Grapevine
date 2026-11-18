"""Who plays the agents the policy is not.

The v0 trainer had a real bug here. Its "frozen collaborators" were built from
the very model object the trainer was updating, so every optimiser step changed
them too: they were not frozen, and a result trained that way would have
measured co-adaptation while describing itself as training against fixed
partners. Nothing was ever trained with it, but the bug was there.

This module makes the distinction explicit and checkable. A partner is one of:

``scripted``
    A deterministic stub for CI and smoke tests. Its turns are tagged
    ``synthetic`` and a trajectory containing one is never a result.
``frozen``
    A *separately loaded* copy of a model, in eval mode with every parameter's
    ``requires_grad`` off. It shares no tensors with the policy, and
    :meth:`HFClient.fingerprint` lets a test prove its weights did not move
    across an optimiser step.
``endpoint``
    An OpenAI-compatible server -- a vLLM or Ollama instance, or a hosted API.
    Frozen by construction, since the trainer cannot reach it.
``self``
    The policy itself, for self-play. **Not frozen, by definition**: one model
    plays every agent and every turn reflects the current weights. The run
    manifest records ``partners_frozen: false`` so this is never mistaken for
    training against fixed partners.

Heavy dependencies (``torch``, ``transformers``) are imported only when a local
model is actually loaded.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from grapevine.rollout.client import (
    Completion,
    LLMClient,
    Message,
    OpenAICompatibleClient,
    ScriptedClient,
)

__all__ = [
    "PARTNER_KINDS",
    "HFClient",
    "PartnerSpec",
    "scripted_partner",
]

PARTNER_KINDS = ("scripted", "frozen", "endpoint", "self")


class HFClient(LLMClient):
    """A local ``transformers`` causal LM behind the client interface.

    Generation runs under ``torch.no_grad`` with the model in eval mode, and the
    model's previous mode is restored afterwards, so the same object can be
    sampled during training (self-play) without leaving dropout off or the
    trainer's mode changed.
    """

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        *,
        model_name: str = "local-hf",
        frozen: bool = False,
    ) -> None:
        """Wrap an already-loaded model and tokenizer.

        Args:
            model: A ``transformers`` causal LM (possibly PEFT-wrapped).
            tokenizer: Its tokenizer.
            model_name: Label recorded in usage and manifests.
            frozen: Whether this client is a frozen partner. Setting it freezes
                the model: eval mode, ``requires_grad`` off everywhere.
        """
        super().__init__(model_name)
        # Not `self.model`: the base class keeps the model's *name* there.
        self.lm = model
        self.tokenizer = tokenizer
        self.frozen = frozen
        if frozen:
            model.eval()
            for parameter in model.parameters():
                parameter.requires_grad_(False)

    @classmethod
    def load(cls, name_or_path: str, *, frozen: bool, device: str = "cpu") -> HFClient:
        """Load a model *afresh* from the Hub or a local path.

        A fresh load is the point: it is the only way to be sure no tensor is
        shared with a model somebody else is training. A directory containing a
        PEFT ``adapter_config.json`` is loaded with its adapter applied.
        """
        from pathlib import Path

        from transformers import AutoModelForCausalLM, AutoTokenizer

        path = Path(name_or_path)
        if (path / "adapter_config.json").exists():
            from peft import AutoPeftModelForCausalLM

            model = AutoPeftModelForCausalLM.from_pretrained(str(path))
        else:
            model = AutoModelForCausalLM.from_pretrained(name_or_path)
        tokenizer = AutoTokenizer.from_pretrained(name_or_path)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model.to(device)
        return cls(model, tokenizer, model_name=name_or_path, frozen=frozen)

    def fingerprint(self) -> str:
        """SHA-256 over every parameter's bytes.

        Two fingerprints taken before and after an optimiser step are equal
        exactly when this model's weights did not change, which is what the
        isolation test asserts for a frozen partner.
        """
        h = hashlib.sha256()
        for name, tensor in sorted(self.lm.state_dict().items()):
            h.update(name.encode("utf-8"))
            h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()

    def render(self, messages: list[Message]) -> str:
        """Messages as one prompt string, via the chat template when there is one."""
        tok = self.tokenizer
        if getattr(tok, "chat_template", None):
            rendered: str = tok.apply_chat_template(
                [{"role": m.role, "content": m.content} for m in messages],
                tokenize=False,
                add_generation_prompt=True,
            )
            return rendered
        return render_plain(messages)

    async def complete(
        self, messages: list[Message], *, max_tokens: int = 256, temperature: float = 0.7
    ) -> Completion:
        """Generate a reply. Greedy when ``temperature`` is 0."""
        import torch

        prompt = self.render(messages)
        device = next(self.lm.parameters()).device
        encoded = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
        encoded = {k: v.to(device) for k, v in encoded.items()}
        prompt_len = int(encoded["input_ids"].shape[1])

        was_training = bool(self.lm.training)
        self.lm.eval()
        try:
            with torch.no_grad():
                output = self.lm.generate(
                    **encoded,
                    max_new_tokens=max_tokens,
                    do_sample=temperature > 0.0,
                    temperature=max(temperature, 1e-5) if temperature > 0.0 else None,
                    top_p=None,
                    top_k=None,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
        finally:
            if was_training and not self.frozen:
                self.lm.train()
        generated = output[0][prompt_len:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        completion = Completion(
            text=text.strip(),
            prompt_tokens=prompt_len,
            completion_tokens=int(generated.shape[0]),
            cost_usd=0.0,
        )
        self._record(completion)
        return completion


def render_plain(messages: list[Message]) -> str:
    """Plain-text rendering for tokenizers without a chat template.

    Also the format GRPO dataset prompts use, so the trained policy sees the
    same rendering at training time and at evaluation time.
    """
    parts = [f"{m.role.upper()}: {m.content}" for m in messages]
    parts.append("ASSISTANT:")
    return "\n\n".join(parts)


# --- Scripted partner ---------------------------------------------------------

_OPTIONS_LINE = re.compile(r"Choose exactly one of these options: (.+?)\.\n")


def _scripted_responder(messages: list[Message]) -> str:
    """A deterministic stand-in for a teammate, for CI only.

    On a discussion turn it acknowledges and says nothing useful. On the
    decision it picks the option named most often in the *discussion* (not in
    its own notes), so the reward genuinely depends on what the policy said,
    while staying offline and instant. It is not a model of a good teammate,
    and nothing trained against it is a result.
    """
    user = messages[-1].content
    match = _OPTIONS_LINE.search(user)
    if match is None:
        return "Noted. I will share what I have when it is useful."
    options = [o.strip() for o in match.group(1).split(",") if o.strip()]
    discussion = user.split("Full team discussion:", 1)[-1].split("Decide the team's answer.")[0]
    counts = {o: len(re.findall(rf"\b{re.escape(o)}\b", discussion)) for o in options}
    best = max(counts.values()) if counts else 0
    choice = next((o for o in options if counts[o] == best), options[0]) if options else ""
    return '{"answer": "' + choice + '"}'


def scripted_partner() -> ScriptedClient:
    """The deterministic CI partner. Its turns are tagged ``synthetic``."""
    return ScriptedClient(_scripted_responder, model="scripted-partner")


# --- Partner specification ----------------------------------------------------


@dataclass(frozen=True)
class PartnerSpec:
    """How the non-trained agents are played, as written in a config file.

    Attributes:
        kind: One of :data:`PARTNER_KINDS`.
        model: For ``frozen``, the model to load separately (defaults to the
            policy's starting checkpoint). For ``endpoint``, the served model
            name.
        base_url: For ``endpoint``, the server's OpenAI-compatible base URL.
    """

    kind: str = "frozen"
    model: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in PARTNER_KINDS:
            raise ValueError(f"partners.kind must be one of {PARTNER_KINDS}, got {self.kind!r}")
        if self.kind == "endpoint" and not (self.model and self.base_url):
            raise ValueError("an endpoint partner needs both partners.model and partners.base_url")

    @property
    def frozen(self) -> bool:
        """Whether partners are fixed for the whole run.

        ``scripted``, ``frozen`` and ``endpoint`` cannot change during training.
        ``self`` is the policy, so it changes every step.
        """
        return self.kind != "self"

    def to_dict(self) -> dict[str, Any]:
        """For the run manifest."""
        return {
            "kind": self.kind,
            "model": self.model,
            "base_url": self.base_url,
            "frozen": self.frozen,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> PartnerSpec:
        """Build from a config file's ``partners`` block."""
        data = dict(data or {})
        unknown = sorted(set(data) - {"kind", "model", "base_url"})
        if unknown:
            raise ValueError(f"unknown partners keys {unknown}")
        return cls(**data)

    def build(self, *, policy_name: str, device: str = "cpu") -> LLMClient:
        """Construct the partner client.

        ``self`` cannot be built here: it needs the trainer's live model, which
        does not exist yet. The trainer binds it after construction.
        """
        if self.kind == "scripted":
            return scripted_partner()
        if self.kind == "frozen":
            return HFClient.load(self.model or policy_name, frozen=True, device=device)
        if self.kind == "endpoint":
            assert self.model is not None and self.base_url is not None
            return OpenAICompatibleClient(self.model, base_url=self.base_url)
        raise ValueError("self-play partners are bound to the trainer's model, not built")


#: A factory returning the client for one agent.
ClientFactory = Callable[[int], LLMClient]
