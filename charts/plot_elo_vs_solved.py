#!/usr/bin/env python3
"""Plot ELO rating vs solve fraction for each agent."""

import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from adjustText import adjust_text

with open("ratings.json") as f:
    data = json.load(f)

DISPLAY_NAMES = {
    "gemini-3-flash-preview (agentic w/ tools)": "Gemini Flash 3 (Agentic)",
    "gemini-3-flash-preview (agentic)": "Gemini Flash 3 (SC)",
    "claude-opus-4-5 (agentic)": "Claude Opus 4.5 (SC)",
    "gemini-3-pro-preview": "Gemini Pro 3",
    "gemini-3-flash-preview": "Gemini Flash 3",
    "claude-opus-4-5": "Claude Opus 4.5",
    "gpt-5.2": "GPT 5.2",
    "goedel": "Goedel Prover V2 32B",
    "multi_tactic": "Tactics",
    "qwen": "Qwen 3",
    "kimina": "Kimina Prover 8B",
}

agents = data["agents"]
elos = [a["strength"] * 173.7 + 1500 for a in agents]
fracs = [a["solved_per_attempt"] for a in agents]
errs = [a["std_error"] * 173.7 for a in agents]
names = [DISPLAY_NAMES.get(a["id"], a["id"]) for a in agents]

fig, ax = plt.subplots(figsize=(12, 7))
ax.errorbar(fracs, elos, yerr=errs, fmt="o", markersize=8, capsize=4, color="steelblue")
texts = [ax.text(f, e, n, fontsize=11) for n, f, e in zip(names, fracs, elos)]
adjust_text(
    texts, x=fracs, y=elos, ax=ax,
    force_text=(3.0, 3.0),
    force_points=(2.0, 2.0),
    expand=(2.5, 2.5),
    min_arrow_len=5,
    iter=500,
    arrowprops=dict(arrowstyle="-", color="gray", lw=0.5),
)
m, b = np.polyfit(fracs, elos, 1)
x_fit = np.linspace(min(fracs), max(fracs), 100)
ax.plot(x_fit, m * x_fit + b, "--", color="tomato", lw=1.5, alpha=0.7)
ax.set_xlabel("Solve Fraction")
ax.set_ylabel("ELO Rating")
ax.set_title("ELO Rating vs Solve Fraction")
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("charts/elo_vs_solved.png", dpi=200, bbox_inches="tight")
print("Saved to charts/elo_vs_solved.png")
