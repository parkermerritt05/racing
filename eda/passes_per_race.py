import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contants import F1_RED, INDY_BLUE, NASCAR_ORANGE

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

race_summary = pd.read_csv(
    os.path.join(REPO_DIR, "position_analysis", "race_summary_all_series.csv")
)
race_lap = pd.read_csv(
    os.path.join(REPO_DIR, "position_analysis", "race_lap_metrics_all_series.csv")
)

race_summary = race_summary.dropna(subset=["total_estimated_swaps"])

# Starting field size per race = field_size on that race's first lap
# (field size only shrinks from there as cars retire).
starting_field_size = (
    race_lap.sort_values("lap")
    .groupby(["series", "year", "race_file"], as_index=False)
    .first()[["series", "year", "race_file", "field_size"]]
    .rename(columns={"field_size": "starting_field_size"})
)

race_summary = race_summary.merge(
    starting_field_size, on=["series", "year", "race_file"], how="left"
)

race_summary["passes_per_car"] = (
    race_summary["total_estimated_swaps"] / race_summary["starting_field_size"]
)

print("Races per series:")
print(race_summary.groupby("series").size())

print("\nAverage estimated passes per race:")
print(race_summary.groupby("series")["total_estimated_swaps"].mean())

print("\nAverage estimated passes per race, normalized by starting field size:")
print(race_summary.groupby("series")["passes_per_car"].mean())

# ============================================================
# PLOT
# ============================================================

sns.set_theme(style="whitegrid", rc={"grid.alpha": 0.3})

palette = {"F1": F1_RED, "IndyCar": INDY_BLUE, "NASCAR": NASCAR_ORANGE}
series_order = ["F1", "IndyCar", "NASCAR"]

fig, axes = plt.subplots(1, 2, figsize=(14, 7))

sns.barplot(
    data=race_summary,
    x="series",
    y="total_estimated_swaps",
    order=series_order,
    hue="series",
    hue_order=series_order,
    palette=palette,
    legend=False,
    errorbar=("ci", 95),
    ax=axes[0],
)
axes[0].set_title("Average estimated passes per race")
axes[0].set_xlabel("Series")
axes[0].set_ylabel("Estimated passes per race")

sns.barplot(
    data=race_summary,
    x="series",
    y="passes_per_car",
    order=series_order,
    hue="series",
    hue_order=series_order,
    palette=palette,
    legend=False,
    errorbar=("ci", 95),
    ax=axes[1],
)
axes[1].set_title("Average estimated passes per race, per car\n(normalized by starting field size)")
axes[1].set_xlabel("Series")
axes[1].set_ylabel("Estimated passes per car")

fig.tight_layout()

output_path = os.path.join(OUTPUT_DIR, "passes_per_race.png")
fig.savefig(output_path, dpi=300)
plt.close(fig)

print(f"\nSaved: {output_path}")
