#!/usr/bin/env python3
"""Render Figure 1: the CORGI pipeline (profile+gate inserted before indexing)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(8, 2.5))
ax.set_xlim(0, 16.4); ax.set_ylim(0, 6); ax.axis("off")

stages = ["Ingest", "Chunk", "Embed", "Profile", "Gate", "Index", "Retrieve", "Generate"]
xs = [1.2 + 2.0 * i for i in range(len(stages))]
y, w, h = 3.4, 1.7, 1.0
corgi = {3, 4}

# dashed CORGI container behind Profile + Gate
cx0, cx1 = xs[3] - w / 2 - 0.22, xs[4] + w / 2 + 0.22
ax.add_patch(FancyBboxPatch((cx0, y - h / 2 - 0.45), cx1 - cx0, h + 0.95,
             boxstyle="round,pad=0.02,rounding_size=0.15", fc="none",
             ec="#1f6fb2", lw=1.6, linestyle="--"))
ax.text((cx0 + cx1) / 2, y + h / 2 + 0.72, "CORGI", ha="center", va="center",
        fontsize=10, color="#1f6fb2", fontweight="bold")

for i, (x, s) in enumerate(zip(xs, stages)):
    hl = i in corgi
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                 boxstyle="round,pad=0.02,rounding_size=0.1",
                 fc=("#d9e8f5" if hl else "#f2f2f2"),
                 ec=("#1f6fb2" if hl else "#888888"), lw=1.3))
    ax.text(x, y, s, ha="center", va="center", fontsize=9)

for i in range(len(xs) - 1):
    ax.add_patch(FancyArrowPatch((xs[i] + w / 2, y), (xs[i + 1] - w / 2, y),
                 arrowstyle="-|>", mutation_scale=12, lw=1.1, color="#555555"))

# quarantine drop-out from the Gate
qx, qy = xs[4], 1.15
ax.add_patch(FancyBboxPatch((qx - 1.7, qy - 0.5), 3.4, 1.0,
             boxstyle="round,pad=0.02,rounding_size=0.1",
             fc="#fbe9e7", ec="#c0392b", lw=1.1))
ax.text(qx, qy, "Quarantine\n(near-dups, thin, truncated)", ha="center", va="center",
        fontsize=7.5, color="#c0392b")
ax.add_patch(FancyArrowPatch((qx, y - h / 2), (qx, qy + 0.5),
             arrowstyle="-|>", mutation_scale=12, lw=1.1, color="#c0392b"))

fig.savefig("../out/fig1_pipeline.png", dpi=220, bbox_inches="tight")
print("wrote ../out/fig1_pipeline.png")
