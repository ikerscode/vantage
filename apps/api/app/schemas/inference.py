from pydantic import BaseModel


class InferenceStatus(BaseModel):
    """What the inference service says about itself, as relayed by
    /api/inference/status — see app/routers/inference.py for why this is
    proxied live rather than read from this process's own env."""

    reachable: bool
    model_backend: str | None = None
    device: str | None = None
