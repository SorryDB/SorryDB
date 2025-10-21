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
    column_details_exclude_list = [User.hashed_password]
    form_excluded_columns = [User.hashed_password, User.agents]
    can_create = True
    can_delete = True
    can_edit = True
    
    def __str__(self, obj):
        return f"{obj.email}"


class AgentAdmin(ModelView, model=Agent):
    name = "Agent"
    name_plural = "Agents"
    column_list = [Agent.id, Agent.name, Agent.visible, Agent.user_id]
    column_searchable_list = [Agent.name, Agent.description]
    column_sortable_list = [Agent.name, Agent.visible]
    form_excluded_columns = [Agent.challenges]
    can_create = True
    can_delete = True
    can_edit = True
    
    def __str__(self, obj):
        return f"{obj.name}"


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
    column_details_exclude_list = [Challenge.submission]
    can_create = True
    can_delete = True
    can_edit = True
    
    def __str__(self, obj):
        return f"Challenge {obj.id[:8]}... ({obj.status.value})"


class SorryAdmin(ModelView, model=SQLSorry):
    name = "SQLSorry"
    name_plural = "SQLSorries"
    identity = "sqlsorry"
    column_list = [
        SQLSorry.id,
        SQLSorry.path,
        SQLSorry.start_line,
        SQLSorry.remote,
        SQLSorry.inclusion_date,
    ]
    column_searchable_list = [SQLSorry.goal, SQLSorry.remote, SQLSorry.path]
    column_sortable_list = [SQLSorry.inclusion_date, SQLSorry.path]
    column_details_exclude_list = [SQLSorry.goal]  # Hide long goal field from details
    form_excluded_columns = [SQLSorry.challenges]
    can_create = False
    can_delete = True
    can_edit = False
    
    def __str__(self, obj):
        filename = obj.path.split("/")[-1] if obj.path else "Unknown"
        return f"{filename}:{obj.start_line}"
