"""All scenario-library reads enforce the authenticated owner, including child rows."""
from sqlalchemy import func, select
from app.models.scenarios import Scenario, ScenarioChangeRecord, ScenarioRun, ScenarioComparison

def owned(db,user_id,scenario_id):
    return db.query(Scenario).filter_by(user_id=user_id,id=scenario_id).one_or_none()

def library(db,user_id,*,status="saved",search="",limit=20,offset=0):
    query=db.query(Scenario).filter(Scenario.user_id==user_id)
    if status=="active":query=query.filter(Scenario.status.in_(["draft","saved"]))
    elif status!="all":query=query.filter(Scenario.status==status)
    if search:
        pattern="%"+search.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        query=query.filter(Scenario.name.ilike(pattern,escape="\\") | Scenario.description.ilike(pattern,escape="\\"))
    total=query.count()
    return query.order_by(Scenario.updated_at.desc(),Scenario.id.desc()).limit(limit).offset(offset).all(),total

def changes(db,user_id,scenario_ids):
    return db.query(ScenarioChangeRecord).join(Scenario,Scenario.id==ScenarioChangeRecord.scenario_id).filter(
        Scenario.user_id==user_id,Scenario.id.in_(scenario_ids)).order_by(ScenarioChangeRecord.id).all()

def latest_runs(db,user_id,scenario_ids):
    ids=select(func.max(ScenarioRun.id)).where(ScenarioRun.user_id==user_id,ScenarioRun.scenario_id.in_(scenario_ids)).group_by(ScenarioRun.scenario_id)
    return {r.scenario_id:r for r in db.query(ScenarioRun).join(Scenario,Scenario.id==ScenarioRun.scenario_id).filter(
        Scenario.user_id==user_id,ScenarioRun.user_id==user_id,ScenarioRun.id.in_(ids)).all()}

def run(db,user_id,scenario_id,run_id=None):
    query=db.query(ScenarioRun).join(Scenario,Scenario.id==ScenarioRun.scenario_id).filter(
        Scenario.user_id==user_id,ScenarioRun.user_id==user_id,ScenarioRun.scenario_id==scenario_id)
    return query.filter(ScenarioRun.id==run_id).one_or_none() if run_id else query.order_by(ScenarioRun.id.desc()).first()

def comparisons(db,user_id,run_id):
    return db.query(ScenarioComparison).join(ScenarioRun,ScenarioRun.id==ScenarioComparison.run_id).join(Scenario,Scenario.id==ScenarioRun.scenario_id).filter(
        Scenario.user_id==user_id,ScenarioRun.user_id==user_id,ScenarioRun.id==run_id).order_by(ScenarioComparison.id).all()

def name_exists(db,user_id,name):
    return db.query(Scenario.id).filter_by(user_id=user_id,name=name).first() is not None
