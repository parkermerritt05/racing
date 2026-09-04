# ============================================================
# START VS FINISH POSITION BY SERIES (95% CI)
#
# Simple EDA chart: for each series, how does average finishing
# position vary with starting position, with a 95% CI band per
# starting position.
#
# Uses the clean start/finish columns already present in each
# series' drivers.csv files (no lap-level reconstruction needed).
# ============================================================

import glob
import os
import re
import sys
import warnings

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import F1_RED, INDY_BLUE, NASCAR_ORANGE

warnings.filterwarnings("ignore")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

SERIES_DIRS = {
    "F1": "f1_data",
    "IndyCar": "indycar_data",
    "NASCAR": "nascar_data",
}


def get_year(path: str):
    m = re.search(r"(?<!\d)20\d{2}(?!\d)", path)
    return int(m.group(0)) if m else None


def load_series(series: str, data_dir: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(REPO_DIR, data_dir, "*", "drivers.csv"))

    frames = []
    for f in files:
        df = pd.read_csv(f, low_memory=False)
        if "start" not in df.columns or "finish" not in df.columns:
            continue

        frames.append(
            pd.DataFrame(
                {
                    "series": series,
                    "year": get_year(f),
                    "race_id": df["race_id"],
                    "start": pd.to_numeric(df["start"], errors="coerce"),
                    "finish": pd.to_numeric(df["finish"], errors="coerce"),
                }
            )
        )

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


data = pd.concat(
    [load_series(series, d) for series, d in SERIES_DIRS.items()],
    ignore_index=True,
)

data = data.dropna(subset=["start", "finish"])

# F1 uses start = 0 for cars starting from pit lane; exclude these.
data = data[~((data["series"] == "F1") & (data["start"] == 0))]

print("Rows per series:")
print(data.groupby("series").size())

# ============================================================
# PLOT
# ============================================================

sns.set_theme(style="whitegrid", rc={"grid.alpha": 0.3})

palette = {"F1": F1_RED, "IndyCar": INDY_BLUE, "NASCAR": NASCAR_ORANGE}

fig, ax = plt.subplots(figsize=(10, 7))

sns.lineplot(
    data=data,
    x="start",
    y="finish",
    hue="series",
    hue_order=["F1", "IndyCar", "NASCAR"],
    palette=palette,
    marker="o",
    markersize=4,
    errorbar=("ci", 95),
    ax=ax,
)

ax.set_title("Start vs finish position by series (95% CI)")
ax.set_xlabel("Starting position")
ax.set_ylabel("Average finish position")
ax.legend(title=None)

fig.tight_layout()

output_path = os.path.join(OUTPUT_DIR, "start_finish_by_series.png")
fig.savefig(output_path, dpi=300)
plt.close(fig)

print(f"Saved: {output_path}")
