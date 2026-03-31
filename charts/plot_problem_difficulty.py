#!/usr/bin/env python3
"""Plot histogram of sorry difficulty ratings."""

import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("ratings.json") as f:
    data = json.load(f)

problems = data["problems"]
elo_diffs = [p["difficulty"] * 173.7 + 1500 for p in problems]

# 14 unique discrete values — count each, plot as equally spaced bars
from collections import Counter
rounded = [round(d, 1) for d in elo_diffs]
counts = Counter(rounded)
unique = sorted(counts.keys())
labels = [f"{int(v)}" for v in unique]
total = sum(counts.values())
pcts = [counts[v] / total * 100 for v in unique]

fig, ax = plt.subplots(figsize=(12, 6))
ax.bar(range(len(unique)), pcts, color="steelblue", edgecolor="white", alpha=0.85)
ax.set_xticks(range(len(unique)))
ax.set_xticklabels(labels, rotation=45, ha="right")
ax.set_xlabel("Sorry Difficulty (ELO)")
ax.set_ylabel("Percentage (%)")
ax.set_title("Sorry Difficulty Distribution")
ax.grid(True, alpha=0.3, axis="y")
plt.tight_layout()
plt.savefig("charts/problem_difficulty_hist.png", dpi=200, bbox_inches="tight")
print(f"Saved to charts/problem_difficulty_hist.png  ({len(problems)} sorries, {len(unique)} unique values)")
