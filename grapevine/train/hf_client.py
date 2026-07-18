"""A local Hugging Face model wrapped as an :class:`LLMClient`.

This lets the exact same multi-agent rollout engine used for API evaluation drive
a locally hosted model -- for example the auxiliary (non-trained) agents during
GRPO reward computation, or a small open model for offline experimentation. It
generates greedily under ``no_grad`` so it does not interfere with training
gradients and yields deterministic auxiliary turns.

The heavy ``torch`` / ``transformers`` imports are deferred to construction time
so importing :mod:`grapevine.train` stays cheap when the training extra is not
installed.
"""

from __future__ import annotations

from typing import Any

from grapevine.rollout.client import Completion, LLMClient, Message


class LocalHFClient(LLMClient):
    """Wrap a ``transformers`` causal LM + tokenizer behind the client interface."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        *,
        model_name: str = "local-hf",
        device: str | None = None,
    ) -> None:
        """Create a client around an already-loaded model and tokenizer.

        Args:
            model: A loaded ``transformers`` causal LM (``AutoModelForCausalLM``).
            tokenizer: The matching tokenizer.
            model_name: Label used for usage reporting.
            device: Device string; defaults to the model's current device.
        """
        super().__init__(model_name)
        self._model = model
        self._tokenizer = tokenizer
        self._device = device or str(getattr(model, "device", "cpu"))

    @classmethod
    def from_pretrained(cls, model_name: str, *, device: str = "cpu") -> LocalHFClient:
        """Load a model + tokenizer by name and wrap them."""
        import torch  # noqa: F401  (imported for side-effect availability check)
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(model_name)
        model.to(device)
        model.eval()
        return cls(model, tokenizer, model_name=model_name, device=device)

    def _render(self, messages: list[Message]) -> str:
        """Render chat messages to a prompt string using the chat template if any."""
        tok = self._tokenizer
        if getattr(tok, "chat_template", None):
            rendered: str = tok.apply_chat_template(
                [{"role": m.role, "content": m.content} for m in messages],
                tokenize=False,
                add_generation_prompt=True,
            )
            return rendered
        # Fallback plain formatting for tokenizers without a chat template.
        parts = [f"{m.role.upper()}: {m.content}" for m in messages]
        parts.append("ASSISTANT:")
        return "\n".join(parts)

    async def complete(
        self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
    ) -> Completion:
        """Generate a completion greedily from the local model."""
        import torch

        prompt = self._render(messages)
        enc = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
        enc = {k: v.to(self._device) for k, v in enc.items()}
        prompt_len = int(enc["input_ids"].shape[1])
        with torch.no_grad():
            out = self._model.generate(
                **enc,
                max_new_tokens=max_tokens,
                do_sample=temperature > 0.0,
                temperature=max(temperature, 1e-5),
                pad_token_id=self._tokenizer.pad_token_id,
            )
        gen_ids = out[0][prompt_len:]
        text = self._tokenizer.decode(gen_ids, skip_special_tokens=True)
        completion_tokens = int(gen_ids.shape[0])
        completion = Completion(
            text=text.strip(),
            prompt_tokens=prompt_len,
            completion_tokens=completion_tokens,
            cost_usd=0.0,
        )
        self._record(completion)
        return completion
