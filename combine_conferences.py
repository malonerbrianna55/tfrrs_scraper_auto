# Script to combine all scraped conference results.
# To be run as an action in GitHub.

import pandas as pd
import glob

files = glob.glob("conference_results/*.csv")

combined = pd.concat(
    [pd.read_csv(file) for file in files],
    ignore_index=True
)

combined.to_csv("ncaa_tfrrs_performances.csv", index=False)