from fastapi import FastAPI

import sorrydb.leaderboard.agents as agents
import sorrydb.leaderboard.challenges as challenges

app = FastAPI()

app.include_router(challenges.router)
app.include_router(agents.router)
