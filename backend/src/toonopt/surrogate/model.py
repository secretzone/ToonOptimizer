"""Small MLP surrogate: gear feature vector -> predicted ``dps / baseline_dps``.

Experimental. ``torch`` (the ``gpu`` extra, ``uv sync --extra gpu``) is only imported
lazily inside :func:`train`/:func:`predict`, and only :func:`train` actually needs it --
a checkpoint's weights are always also serialised as plain numpy arrays (a handful of
``np.savez``-style arrays inside the ``.pt`` file, not a real torch archive), so
:func:`predict` and :func:`status` work with plain numpy even on a machine that never
installed torch. When torch *and* CUDA *are* available, :func:`predict` still runs the
forward pass on the GPU in batches for speed; otherwise it falls back to a manual numpy
forward pass with the same weights.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from toonopt.config import RUNTIME_DIR
from toonopt.models import now_iso
from toonopt.surrogate.features import FEATURE_VERSION

log = logging.getLogger(__name__)

MODEL_DIR = RUNTIME_DIR / "surrogate"
HIDDEN = (128, 64, 32)
DROPOUT = 0.2
DEFAULT_EPOCHS = 200
BATCH_SIZE = 256
PREDICT_BATCH = 8192


class SurrogateUnavailable(RuntimeError):
    """torch is not installed; training needs it (`uv sync --extra gpu`)."""


class NotTrained(RuntimeError):
    """No trained checkpoint for this (klass, spec), or it is stale (feature version)."""


@dataclass
class TrainReport:
    samples: int
    val_mae_pct: float
    epochs: int
    device: str
    path: str


def _model_path(klass: str, spec: str) -> Path:
    return MODEL_DIR / f"{klass}_{spec}.pt"


def has_model(klass: str, spec: str) -> bool:
    return _model_path(klass, spec).exists()


def _torch() -> Any:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError as e:
        raise SurrogateUnavailable("torch is not installed; run `uv sync --extra gpu`") from e
    return torch


def device_name() -> str:
    """'cuda' / 'cpu' if torch is importable, else 'unavailable'."""
    try:
        torch = _torch()
    except SurrogateUnavailable:
        return "unavailable"
    return "cuda" if torch.cuda.is_available() else "cpu"


class _NumpyNet:
    """Torch-free ReLU-MLP forward pass, built from a trained model's raw weights."""

    def __init__(self, weights: list[np.ndarray], biases: list[np.ndarray]):
        self.weights = weights
        self.biases = biases

    def forward(self, x: np.ndarray) -> np.ndarray:
        h = x
        n = len(self.weights)
        for i, (w, b) in enumerate(zip(self.weights, self.biases, strict=True)):
            h = h @ w.T + b
            if i < n - 1:
                h = np.maximum(h, 0.0, out=h)
        return h.reshape(-1)


def _save(path: Path, weights: list[np.ndarray], biases: list[np.ndarray], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {f"w{i}": w for i, w in enumerate(weights)}
    arrays.update({f"b{i}": b for i, b in enumerate(biases)})
    arrays["n_layers"] = np.array([len(weights)])
    arrays["meta"] = np.array(json.dumps(meta))
    with open(path, "wb") as f:
        np.savez(f, **arrays)


def _load(path: Path) -> tuple[_NumpyNet, dict]:
    with open(path, "rb") as f:
        data = np.load(f, allow_pickle=False)
        n = int(data["n_layers"][0])
        weights = [data[f"w{i}"] for i in range(n)]
        biases = [data[f"b{i}"] for i in range(n)]
        meta = json.loads(str(data["meta"]))
    return _NumpyNet(weights, biases), meta


_CACHE: dict[tuple[str, str], tuple[_NumpyNet, dict]] = {}


def _get(klass: str, spec: str) -> tuple[_NumpyNet, dict]:
    key = (klass, spec)
    path = _model_path(klass, spec)
    if not path.exists():
        _CACHE.pop(key, None)
        raise NotTrained(f"no trained surrogate for {klass}/{spec}; POST /api/surrogate/train first")
    mtime = path.stat().st_mtime
    cached = _CACHE.get(key)
    if cached is not None and cached[1].get("_mtime") == mtime:
        return cached
    net, meta = _load(path)
    if meta.get("feature_version") != FEATURE_VERSION:
        raise NotTrained(
            f"surrogate for {klass}/{spec} was trained against feature layout "
            f"v{meta.get('feature_version')}, current is v{FEATURE_VERSION}; retrain it"
        )
    meta["_mtime"] = mtime
    _CACHE[key] = (net, meta)
    return _CACHE[key]


def train(
    klass: str,
    spec: str,
    min_samples: int = 200,
    epochs: int = DEFAULT_EPOCHS,
    progress_cb: Any = None,
) -> TrainReport:
    """Train an MLP on this (klass, spec)'s sim history and save it under RUNTIME_DIR.

    ``progress_cb(epoch, total_epochs, val_mae)`` is called once per epoch when given.
    Raises :class:`SurrogateUnavailable` if torch is not installed and ``ValueError`` if
    there are fewer than ``min_samples`` usable rows.
    """
    from toonopt.surrogate import dataset as dataset_mod

    torch = _torch()
    from torch import nn

    ds = dataset_mod.build(klass, spec)
    n = len(ds)
    if n < min_samples:
        raise ValueError(
            f"only {n} training rows for {klass}/{spec} (need >= {min_samples}); "
            "run more Top Gear / Droptimizer / Gear Compare jobs for this spec first"
        )

    X = ds.X
    y = ds.y
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std < 1e-6] = 1.0
    Xn = (X - mean) / std

    rng = np.random.default_rng(0)
    idx = rng.permutation(n)
    n_val = max(1, int(n * 0.15))
    val_idx, train_idx = idx[:n_val], idx[n_val:]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    Xt = torch.tensor(Xn[train_idx], dtype=torch.float32, device=device)
    yt = torch.tensor(y[train_idx], dtype=torch.float32, device=device)
    Xv = torch.tensor(Xn[val_idx], dtype=torch.float32, device=device)
    yv = torch.tensor(y[val_idx], dtype=torch.float32, device=device)

    sizes = [X.shape[1], *HIDDEN, 1]
    layers: list[Any] = []
    for i in range(len(sizes) - 2):
        layers += [nn.Linear(sizes[i], sizes[i + 1]), nn.ReLU(), nn.Dropout(DROPOUT)]
    layers.append(nn.Linear(sizes[-2], sizes[-1]))
    net = nn.Sequential(*layers).to(device)

    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-5)
    loss_fn = nn.MSELoss()
    val_mae = float("inf")
    n_train = Xt.shape[0]
    for epoch in range(1, epochs + 1):
        net.train()
        perm = torch.randperm(n_train, device=device)
        for s in range(0, n_train, BATCH_SIZE):
            b = perm[s:s + BATCH_SIZE]
            opt.zero_grad()
            pred = net(Xt[b]).squeeze(-1)
            loss = loss_fn(pred, yt[b])
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            pred_v = net(Xv).squeeze(-1)
            val_mae = torch.mean(torch.abs(pred_v - yv)).item()
        if progress_cb:
            progress_cb(epoch, epochs, val_mae)

    weights: list[np.ndarray] = []
    biases: list[np.ndarray] = []
    for layer in net:
        if isinstance(layer, nn.Linear):
            weights.append(layer.weight.detach().cpu().numpy().astype(np.float32))
            biases.append(layer.bias.detach().cpu().numpy().astype(np.float32))

    val_mae_pct = round(val_mae * 100.0, 3)
    path = _model_path(klass, spec)
    meta = {
        "klass": klass, "spec": spec, "samples": n, "val_mae_pct": val_mae_pct,
        "epochs": epochs, "device": device, "feature_version": FEATURE_VERSION,
        "trained_at": now_iso(), "mean": mean.tolist(), "std": std.tolist(),
    }
    _save(path, weights, biases, meta)
    _CACHE.pop((klass, spec), None)
    return TrainReport(samples=n, val_mae_pct=val_mae_pct, epochs=epochs, device=device, path=str(path))


def predict(klass: str, spec: str, vectors: np.ndarray) -> np.ndarray:
    """Predict ``dps / baseline_dps`` for a batch of feature vectors (shape (N, VECTOR_LENGTH))."""
    net, meta = _get(klass, spec)
    x = np.asarray(vectors, dtype=np.float32)
    if x.ndim == 1:
        x = x[None, :]
    mean = np.asarray(meta["mean"], dtype=np.float32)
    std = np.asarray(meta["std"], dtype=np.float32)
    xn = (x - mean) / std

    try:
        torch = _torch()
        if torch.cuda.is_available():
            with torch.no_grad():
                device = "cuda"
                h = torch.tensor(xn, dtype=torch.float32, device=device)
                n = len(net.weights)
                for i, (w, b) in enumerate(zip(net.weights, net.biases, strict=True)):
                    h = h @ torch.tensor(w, dtype=torch.float32, device=device).T
                    h = h + torch.tensor(b, dtype=torch.float32, device=device)
                    if i < n - 1:
                        h = torch.relu(h)
                return h.reshape(-1).cpu().numpy()
    except SurrogateUnavailable:
        pass
    out_chunks = [net.forward(xn[s:s + PREDICT_BATCH]) for s in range(0, len(xn), PREDICT_BATCH)]
    return np.concatenate(out_chunks) if out_chunks else np.zeros(0, dtype=np.float32)


def status() -> dict:
    dev = device_name()
    models: list[dict] = []
    if MODEL_DIR.exists():
        for p in sorted(MODEL_DIR.glob("*.pt")):
            try:
                _, meta = _load(p)
            except (ValueError, OSError, KeyError):
                log.warning("could not read surrogate checkpoint %s", p)
                continue
            models.append({
                "klass": meta.get("klass"), "spec": meta.get("spec"),
                "samples": meta.get("samples"), "val_mae_pct": meta.get("val_mae_pct"),
                "trained_at": meta.get("trained_at"),
            })
    return {"available": dev != "unavailable", "device": dev, "models": models}
