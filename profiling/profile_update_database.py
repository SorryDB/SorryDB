#!/usr/bin/env python3

import logging
from pathlib import Path
import subprocess
import os
import cProfile

from sorrydb.database.build_database import update_database

# Start profiler
profiler = cProfile.Profile()
profiler.enable()

# Configure logging
log_kwargs = {
    "level": "DEBUG",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
}
logging.basicConfig(**log_kwargs)

logger = logging.getLogger(__name__)

# Run code you want to profile
update_database(database_path=Path("/data/sorry_database.json"))

# Evaluate profile and produce a nice visualization (profile.png)
profiler.disable()
logger.info("dumping stats to p.prof")
profiler.dump_stats("/data/p.prof")
#
# try:
#     subprocess.run("gprof2dot -f pstats p.prof -n 0.005 -e 0.001 | dot -Tpng -o profile.png")
# except subprocess.CalledProcessError:
#     print("gprof2dot or dot is not installed. Skipping profile visualization.")

