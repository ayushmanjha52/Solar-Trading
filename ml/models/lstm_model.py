"""Sequence model: an LSTM over the last 48 hours of metered energy, with quantile heads.

Input: 96 half-hours of (net, gen, load) ending at t-2, plus what is known
about the target slot in advance (PV capacity, sun elevation, time of day,
day of week, month). Output: P10, P50 and P90 of net energy at t, trained on
the pinball loss. P10 and P90 are built as P50 minus/plus a softplus, so the
quantiles cannot cross by construction.

Why it might lose to the trees: two steps ahead, the most recent observation
carries most of the signal, and the tabular model is handed it directly. The
LSTM has to learn to find it. It is reported either way.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from ml.features import build_features as bf
from ml.models.baselines import QUANTILES

STATIC = ["pv_kwp", "sun_elev", "slot", "dow", "month"]


def static_block(f: dict, idx: np.ndarray) -> np.ndarray:
    slot, dow, month = f["slot"][idx], f["dow"][idx], f["month"][idx]
    return np.column_stack([
        f["pv_kwp"][idx] / 5.0,
        np.clip(f["sun_elev"][idx], -10, 90) / 90.0,
        np.sin(2 * np.pi * slot / 48), np.cos(2 * np.pi * slot / 48),
        np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
        np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12),
    ]).astype(np.float32)


class QuantileLSTM(nn.Module):
    def __init__(self, n_static: int = 8, hidden: int = 64):
        super().__init__()
        self.lstm = nn.LSTM(input_size=3, hidden_size=hidden, num_layers=1, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden + n_static, 64), nn.ReLU(), nn.Linear(64, 3))

    def forward(self, seq: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        _, (h, _) = self.lstm(seq)
        out = self.head(torch.cat([h[-1], static], dim=1))
        mid = out[:, 1]
        lo = mid - nn.functional.softplus(out[:, 0])
        hi = mid + nn.functional.softplus(out[:, 2])
        return torch.stack([lo, mid, hi], dim=1)


def pinball(pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    q = torch.tensor(QUANTILES, dtype=pred.dtype)
    diff = y[:, None] - pred
    return torch.maximum(q * diff, (q - 1) * diff).mean()


class Windows:
    """Draws (sequence, static, target) batches straight from household arrays by fancy indexing."""

    def __init__(self, series: list[bf.Series], feats: list[dict]):
        self.stack = [np.stack([s.net_wh, s.gen_wh, s.load_wh], axis=1).astype(np.float32) / 1000 for s in series]
        self.feats = feats
        self.y = [s.net_wh.astype(np.float32) / 1000 for s in series]
        self.offsets = np.arange(-bf.HORIZON - bf.SEQ_LEN + 1, -bf.HORIZON + 1)

    def batch(self, which: np.ndarray, t: np.ndarray):
        seq = np.empty((len(t), bf.SEQ_LEN, 3), np.float32)
        stat = np.empty((len(t), 8), np.float32)
        y = np.empty(len(t), np.float32)
        for k in np.unique(which):
            m = which == k
            seq[m] = self.stack[k][t[m][:, None] + self.offsets[None, :]]
            stat[m] = static_block(self.feats[k], t[m])
            y[m] = self.y[k][t[m]]
        return torch.from_numpy(seq), torch.from_numpy(stat), torch.from_numpy(y)


def train(win: Windows, train_pairs: tuple[np.ndarray, np.ndarray], val_pairs: tuple[np.ndarray, np.ndarray],
          epochs: int = 12, steps_per_epoch: int = 600, batch: int = 512, seed: int = 0, log=print) -> QuantileLSTM:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = QuantileLSTM()
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    vw, vt = val_pairs
    vsel = rng.choice(len(vt), size=min(40_000, len(vt)), replace=False)
    best, best_state, patience = np.inf, None, 0
    for epoch in range(epochs):
        model.train()
        for _ in range(steps_per_epoch):
            i = rng.integers(0, len(train_pairs[1]), batch)
            seq, stat, y = win.batch(train_pairs[0][i], train_pairs[1][i])
            loss = pinball(model(seq, stat), y)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
        val = evaluate_loss(model, win, vw[vsel], vt[vsel])
        log(f"lstm      epoch {epoch + 1:2d}  val pinball {val * 1000:.1f} Wh")
        if val < best - 1e-5:
            best, best_state, patience = val, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 3:
                break
    model.load_state_dict(best_state)
    return model


@torch.no_grad()
def evaluate_loss(model: QuantileLSTM, win: Windows, which: np.ndarray, t: np.ndarray) -> float:
    model.eval()
    losses = []
    for s in range(0, len(t), 8192):
        seq, stat, y = win.batch(which[s:s + 8192], t[s:s + 8192])
        losses.append(pinball(model(seq, stat), y).item() * len(y))
    return sum(losses) / len(t)


@torch.no_grad()
def predict(model: QuantileLSTM, win: Windows, which: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Quantile predictions in Wh."""
    model.eval()
    out = []
    for s in range(0, len(t), 8192):
        seq, stat, _ = win.batch(which[s:s + 8192], t[s:s + 8192])
        out.append(model(seq, stat).numpy())
    return np.vstack(out) * 1000
