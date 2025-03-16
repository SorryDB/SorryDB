#!/usr/bin/env python3

from pathlib import Path
import subprocess
import os
import cProfile

from sorrydb.database.build_database import update_database

# Start profiler
profiler = cProfile.Profile()
profiler.enable()


# Run code you want to profile
update_database(database_path=Path("sorry_database.json"))

# Evaluate profile and produce a nice visualization (profile.png)
profiler.disable()
profiler.dump_stats("p.prof")

try:
    subprocess.run("gprof2dot -f pstats p.prof -n 0.005 -e 0.001 | dot -Tpng -o profile.png")
except subprocess.CalledProcessError:
    print("gprof2dot or dot is not installed. Skipping profile visualization.")

os.remove("p.prof")
