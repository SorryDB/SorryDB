from fastapi import FastAPI

import sorrydb.leaderboard.api.agents as agents
import sorrydb.leaderboard.api.challenges as challenges

app = FastAPI()

app.include_router(challenges.router)
app.include_router(agents.router)
