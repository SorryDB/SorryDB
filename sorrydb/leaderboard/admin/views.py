from sqladmin import ModelView

from sorrydb.leaderboard.model.agent import Agent
from sorrydb.leaderboard.model.challenge import Challenge
from sorrydb.leaderboard.model.sorry import SQLSorry
from sorrydb.leaderboard.model.user import User


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    column_list = [User.id, User.email, User.is_admin, User.is_active, User.created_at]
    column_searchable_list = [User.email]
    column_sortable_list = [User.email, User.created_at, User.is_admin]
    can_create = False
    can_delete = True
    can_edit = True


class AgentAdmin(ModelView, model=Agent):
    name = "Agent"
    name_plural = "Agents"
    column_list = [Agent.id, Agent.name, Agent.user_id]
    column_searchable_list = [Agent.name]
    column_sortable_list = [Agent.name]
    can_create = True
    can_delete = True
    can_edit = True


class ChallengeAdmin(ModelView, model=Challenge):
    name = "Challenge"
    name_plural = "Challenges"
    column_list = [
        Challenge.id,
        Challenge.status,
        Challenge.deadline,
        Challenge.agent_id,
        Challenge.sorry_id,
    ]
    column_sortable_list = [Challenge.deadline, Challenge.status]
    can_create = True
    can_delete = True
    can_edit = True


class SorryAdmin(ModelView, model=SQLSorry):
    name = "SQLSorry"
    name_plural = "SQLSorries"
    identity = "sqlsorry"  # This determines the URL segment
    column_list = [
        SQLSorry.id,
        SQLSorry.goal,
        SQLSorry.remote,
        SQLSorry.path,
        SQLSorry.inclusion_date,
    ]
    column_searchable_list = [SQLSorry.goal, SQLSorry.remote]
    column_sortable_list = [SQLSorry.inclusion_date]
    can_create = False
    can_delete = True
    can_edit = False
