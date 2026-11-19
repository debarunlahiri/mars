"""Pick the compute device for local models: NVIDIA GPU (CUDA) > Apple GPU (Metal/MPS) > CPU."""

from __future__ import annotations

from functools import lru_cache

from ..core.logging import get_logger

log = get_logger("device")


@lru_cache
def available_devices() -> tuple[str, ...]:
    """Devices PyTorch can use here, best first. Without torch only the CPU is reported."""
    found: list[str] = []
    try:
        import torch

        if torch.cuda.is_available():
            found.append("cuda")
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            found.append("mps")
    except Exception:  # noqa: BLE001 - torch missing or broken: CPU only
        pass
    found.append("cpu")
    return tuple(found)


def resolve_device(preference: str = "auto") -> str:
    """``auto`` picks the best device; an explicit but unavailable choice falls back with a warning."""
    available = available_devices()
    if preference == "auto":
        return available[0]
    if preference in available:
        return preference
    log.warning("device %r is not available (have: %s); using %s", preference, ", ".join(available), available[0])
    return available[0]


def onnx_providers(device: str) -> list[str]:
    """ONNX Runtime execution providers for ``device`` (used by fastembed and OCR), CPU last."""
    try:
        import onnxruntime

        have = set(onnxruntime.get_available_providers())
    except Exception:  # noqa: BLE001
        return ["CPUExecutionProvider"]
    wanted = {"cuda": "CUDAExecutionProvider", "mps": "CoreMLExecutionProvider"}.get(device)
    return ([wanted] if wanted in have else []) + ["CPUExecutionProvider"]


def describe_device(device: str) -> str:
    try:
        import torch

        if device == "cuda":
            return f"cuda ({torch.cuda.get_device_name(0)})"
    except Exception:  # noqa: BLE001
        pass
    return {"mps": "mps (Apple GPU)", "cpu": "cpu"}.get(device, device)
