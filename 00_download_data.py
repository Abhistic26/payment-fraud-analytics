"""
=============================================================================
 STAGE 00 : Data Acquisition
=============================================================================
 SOURCE
 ------
 Université Libre de Bruxelles (ULB) Machine Learning Group -- transaction
 data released alongside the open handbook:

   "Reproducible Machine Learning for Credit Card Fraud Detection --
    Practical Handbook"  (Le Borgne, Siblini, Lebichot & Bontempi, 2022)
   https://fraud-detection-handbook.github.io/fraud-detection-handbook/

 The data is published as one pickle file per day. This script pulls the
 92-day window used in the analysis (2018-04-01 to 2018-07-01).

 WHY THIS SOURCE
 ---------------
 Production card data is never public. This is the reference dataset the
 fraud-detection research community uses precisely because it reproduces
 the structural properties of real card portfolios -- extreme class
 imbalance, entity-level attack patterns, and time-dependent behaviour --
 while being freely redistributable. Provenance is stated openly rather
 than implied; see README for the full note on data realism.

 NOTE: raw files are gitignored (~130 MB). Run this script once after
 cloning, then run 01 -> 02 -> 03 -> 04.
=============================================================================
"""

import os
import sys
import urllib.request
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

BASE_URL = ("https://raw.githubusercontent.com/Fraud-Detection-Handbook/"
            "simulated-data-raw/main/data")
DEST = os.path.join(os.path.dirname(__file__), "..", "data")
START = date(2018, 4, 1)
N_DAYS = 92

os.makedirs(DEST, exist_ok=True)


def fetch(day):
    ds = day.isoformat()
    path = os.path.join(DEST, f"hb_{ds}.pkl")
    if os.path.exists(path) and os.path.getsize(path) > 10_000:
        return ("cached", ds)
    try:
        urllib.request.urlretrieve(f"{BASE_URL}/{ds}.pkl", path)
        return ("ok", ds)
    except Exception as e:
        if os.path.exists(path):
            os.remove(path)
        return ("fail", f"{ds}: {e}")


def main():
    days = [START + timedelta(i) for i in range(N_DAYS)]
    print(f"Fetching {len(days)} daily files "
          f"({days[0]} -> {days[-1]}) from ULB handbook repo ...")

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch, days))

    ok = sum(1 for s, _ in results if s == "ok")
    cached = sum(1 for s, _ in results if s == "cached")
    fails = [m for s, m in results if s == "fail"]

    print(f"  downloaded : {ok}")
    print(f"  cached     : {cached}")
    print(f"  failed     : {len(fails)}")
    for f in fails[:5]:
        print(f"    - {f}")

    if fails:
        print("\nSome files failed. Re-run this script -- completed files are "
              "cached and will be skipped.")
        sys.exit(1)

    total = sum(
        os.path.getsize(os.path.join(DEST, f))
        for f in os.listdir(DEST) if f.startswith("hb_")
    )
    print(f"\n[OK] {ok + cached} files | {total/1024/1024:.1f} MB")
    print("Next: python notebooks/01_etl_star_schema.py")


if __name__ == "__main__":
    main()
