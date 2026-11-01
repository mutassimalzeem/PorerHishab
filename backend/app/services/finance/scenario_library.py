"""AI-15R lifecycle and comparison orchestration. No financial arithmetic lives here."""
from collections import Counter
from datetime import datetime, timezone
import json
from fastapi import HTTPException
from app.models.scenarios import Scenario, ScenarioChangeRecord
from app.repositories import scenarios as repository
from app.schemas.scenarios import (ScenarioLibraryPage, ScenarioLibraryComparison, ScenarioCompareColumn,
    AssumptionComparison, ScenarioMetricRow, ScenarioMetricCell)
from app.services.finance import scenarios as simulator
from app.services.finance.goal_planning import lock_user


def listing(db, user_id, *, status="saved", search="", limit=20, offset=0):
    rows,total=repository.library(db,user_id,status=status,search=search.strip(),limit=limit,offset=offset)
    ids=[r.id for r in rows]
    latest=repository.latest_runs(db,user_id,ids)
    changes={sid:[] for sid in ids}
    for change in repository.changes(db,user_id,ids):changes[change.scenario_id].append(change)
    return ScenarioLibraryPage(items=[simulator.read(db,r,latest=latest.get(r.id),changes=changes[r.id]) for r in rows],total=total,limit=limit,offset=offset)


def update_metadata(db,user_id,scenario_id,payload):
    lock_user(db,user_id);row=simulator.owned(db,user_id,scenario_id);simulator.editable(row)
    changed=False
    for field,value in payload.model_dump(exclude_unset=True).items():
        if getattr(row,field)!=value:setattr(row,field,value);changed=True
    if changed:row.updated_at=datetime.now(timezone.utc)
    # Metadata deliberately does not advance the financial assumption revision.
    db.commit();return simulator.read(db,row)


def duplicate(db,user_id,scenario_id):
    lock_user(db,user_id);source=simulator.owned(db,user_id,scenario_id)
    number=1
    while True:
        suffix=" (Copy)" if number==1 else f" (Copy {number})"
        name=source.name[:120-len(suffix)].rstrip()+suffix
        if not repository.name_exists(db,user_id,name):break
        number+=1
    row=Scenario(user_id=user_id,name=name,description=source.description,status="draft",source_scenario_id=source.id,
        calculation_version=source.calculation_version)
    db.add(row);db.flush()
    for change in simulator.changes_for(db,source):db.add(ScenarioChangeRecord(scenario_id=row.id,**change.model_dump()))
    # Runs/reference/timestamps are intentionally independent; no auto-simulation.
    db.commit();return simulator.read(db,row)


def restore(db,user_id,scenario_id):
    lock_user(db,user_id);row=simulator.owned(db,user_id,scenario_id)
    if row.status=="saved":return simulator.read(db,row)
    if row.status!="archived":raise HTTPException(409,"Only archived scenarios can be restored")
    now=datetime.now(timezone.utc)
    row.status="saved";row.archived_at=None;row.updated_at=now;row.saved_at=row.saved_at or now
    db.commit();return simulator.read(db,row)


def signature(change):
    return json.dumps(change.model_dump(mode="json"),sort_keys=True)


def compare(db,user_id,payload):
    # Same owner lock as Q simulation/mutations gives a coherent read of selected revisions.
    lock_user(db,user_id)
    rows=[simulator.owned(db,user_id,sid) for sid in payload.scenario_ids]
    latest=repository.latest_runs(db,user_id,payload.scenario_ids)
    details=[simulator.read(db,r,latest=latest.get(r.id)) for r in rows]
    versions={latest[r.id].calculation_version for r in rows if r.id in latest}
    if len(versions)>1:raise HTTPException(409,"Selected results use incompatible calculation versions; explicitly rerun scenarios before comparing")
    results=[simulator.result_for(db,user_id,r.id,latest[r.id].id) if d.result_state=="current" else None for r,d in zip(rows,details)]
    counts=[Counter(signature(c) for c in d.changes) for d in details]
    shared=counts[0].copy()
    for count in counts[1:]:shared &= count
    columns=[]
    for detail,result in zip(details,results):
        remaining=shared.copy();assumptions=[]
        for change in detail.changes:
            key=signature(change);common=remaining[key]>0
            if common:remaining[key]-=1
            assumptions.append(AssumptionComparison(change=change,shared=common))
        columns.append(ScenarioCompareColumn(scenario=detail,result=result,assumptions=assumptions))
    metric_names=sorted({m.metric for result in results if result for m in result.comparisons})
    indices=[{m.metric:m for m in result.comparisons} if result else {} for result in results]
    matrix=[]
    for name in metric_names:
        cells=[]
        for detail,index in zip(details,indices):
            metric=index.get(name)
            reason=("No simulation result exists; open and explicitly run this scenario." if detail.result_state=="missing" else
                    "Assumptions or calculation version changed since the last run; explicitly rerun this scenario." if detail.result_state=="stale" else
                    "The stored result does not expose this metric.")
            cells.append(ScenarioMetricCell(scenario_id=detail.id,comparison=metric,status=metric.status if metric else "insufficient_data",reason=metric.reason if metric else reason))
        matrix.append(ScenarioMetricRow(metric=name,cells=cells))
    warnings=[]
    if any(d.result_state=="missing" for d in details):warnings.append("missing_results")
    if any(d.result_state=="stale" for d in details):warnings.append("stale_results")
    available=[r for r in results if r]
    for attribute,warning in [("baseline_snapshot_reference","different_baselines"),("baseline_snapshot_date","different_snapshot_dates"),("horizon_end","different_horizons")]:
        if len({getattr(r,attribute) for r in available})>1:warnings.append(warning)
    if len({latest[r.scenario_id].request.get("schedules_confirmed") for r in available})>1:warnings.append("different_schedule_confirmations")
    return ScenarioLibraryComparison(columns=columns,metrics=matrix,calculation_version=next(iter(versions),None),warnings=warnings)
