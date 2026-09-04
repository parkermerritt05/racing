# Racing

The goal of this project is to compare the relative importance of qualifying accross F1, IndyCar, and NASCAR.

## Data
- **data_scraping/** — pulls race results into structured datasets for each series (F1, IndyCar, NASCAR)
- **f1_data/**, **indycar_data/**, **nascar_data/** — built datasets per series

## Analysis
- **analysis.ipynb** — main notebook analyzing the importance of qualifying with partial R^2 results, adjusting for various measures of performance.
- **eda/** — exploratory plots (e.g. passes per race, start vs. finish position by series)
- **position_analysis/** — cross-series comparison of position changes and race volatility
- **qualifying_vs_race_analysis/**, **qualifying_importance_analysis/** — how well qualifying position predicts race outcome
