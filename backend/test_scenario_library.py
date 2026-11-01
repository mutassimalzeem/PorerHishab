"""Library operations organize Q assumptions/results and never calculate finances."""
from datetime import timedelta,datetime,timezone
from decimal import Decimal as D
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event
from test_goal_planning import data,seed,DAY
from test_scenarios import setup,run,change,state
from app.main import app
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.scenarios import Scenario,ScenarioRun
from app.schemas.scenarios import ScenarioCreate,ScenarioMetadataUpdate,ScenarioCompareRequest,ChangesRequest
from app.services.finance import scenarios as q,scenario_library as library


def saved(db,user,name="Alternative",changes=()):
    row=setup(db,user,changes);library.update_metadata(db,user.id,row.id,ScenarioMetadataUpdate(name=name))
    return q.set_status(db,user.id,row.id,"saved")


def test_library_status_search_pagination_order_and_literal_search(data):
    db,users=data
    one=saved(db,users[0],"Rent +5%");two=saved(db,users[0],"Salary");draft=setup(db,users[0]);foreign=saved(db,users[1],"Rent +5%")
    q.set_status(db,users[0].id,two.id,"archived")
    assert [r.id for r in library.listing(db,users[0].id).items]==[one.id]
    assert library.listing(db,users[0].id,status="archived").items[0].id==two.id
    assert library.listing(db,users[0].id,status="draft").items[0].id==draft.id
    assert library.listing(db,users[0].id,status="active").total==2
    assert library.listing(db,users[0].id,status="all",search="%").total==1
    assert library.listing(db,users[0].id,status="all",search="_").total==0
    library.update_metadata(db,users[0].id,one.id,ScenarioMetadataUpdate(description="Future housing budget"))
    assert library.listing(db,users[0].id,search="HOUSING").total==1
    for row in db.query(Scenario).filter_by(user_id=users[0].id):row.updated_at=datetime(2026,11,1,tzinfo=timezone.utc)
    db.commit()
    first=library.listing(db,users[0].id,status="all",limit=1);second=library.listing(db,users[0].id,status="all",limit=1,offset=1)
    assert first.total==3 and first.items[0].id==draft.id and second.items[0].id==two.id


def test_metadata_normalization_does_not_stale_result(data):
    db,users=data;seed(db,users[0]);row=saved(db,users[0]);result=run(db,users[0],row)
    before=state(db);renamed=library.update_metadata(db,users[0].id,row.id,ScenarioMetadataUpdate(name="  New   plan  ",description="Salary rises but do not change assumptions"))
    assert renamed.name=="New plan" and renamed.revision==row.revision
    assert renamed.result_state=="current" and renamed.latest_run_id==result.run_id
    assert renamed.latest_run_at and renamed.saved_at and state(db)==before
    assert renamed.changes==row.changes


@pytest.mark.parametrize("payload",[{"name":"   "},{"name":"x"*121},{"name":None},{"description":None},{},{"status":"archived"},{"changes":[]}])
def test_metadata_validation(payload):
    with pytest.raises(ValidationError):ScenarioMetadataUpdate(**payload)


def test_create_names_normalize_but_not_globally_unique(data):
    db,users=data
    for user in users:
        assert q.create(db,user.id,ScenarioCreate(name="  Same   plan ")).name=="Same plan"
    with pytest.raises(ValidationError):ScenarioCreate(name=" ")


def test_duplicate_has_independent_lifecycle_and_no_inherited_results(data):
    db,users=data;seed(db,users[0]);row=saved(db,users[0],"Rent",[change("recurring_expense_adjustment","500")]);result=run(db,users[0],row)
    before=state(db);original=q.read(db,q.owned(db,users[0].id,row.id))
    copied=library.duplicate(db,users[0].id,row.id);again=library.duplicate(db,users[0].id,row.id)
    assert copied.id!=row.id and copied.source_scenario_id==row.id and copied.changes==row.changes
    assert copied.name=="Rent (Copy)" and again.name=="Rent (Copy 2)"
    assert copied.status=="draft" and copied.saved_at is None and copied.archived_at is None
    assert copied.created_at>=row.created_at and copied.latest_run_id is None and copied.base_snapshot_reference is None
    assert q.read(db,q.owned(db,users[0].id,row.id))==original and state(db)==before
    q.replace_changes(db,users[0].id,copied.id,ChangesRequest(changes=[]))
    assert q.changes_for(db,q.owned(db,users[0].id,row.id))==row.changes


def test_archive_restore_is_natural_idempotency_and_preserves_history(data):
    db,users=data;seed(db,users[0]);row=saved(db,users[0],changes=[change("income_adjustment","1000")]);result=run(db,users[0],row)
    before=state(db);archived=q.set_status(db,users[0].id,row.id,"archived")
    assert archived.archived_at and library.listing(db,users[0].id).total==0
    assert q.set_status(db,users[0].id,row.id,"archived").archived_at==archived.archived_at
    assert q.result_for(db,users[0].id,row.id)==result
    restored=library.restore(db,users[0].id,row.id)
    assert restored.id==row.id and restored.status=="saved" and restored.archived_at is None and restored.changes==row.changes
    assert library.restore(db,users[0].id,row.id).updated_at==restored.updated_at
    assert q.result_for(db,users[0].id,row.id)==result and state(db)==before


def test_comparison_reuses_exact_results_and_assumption_multisets(data,monkeypatch):
    db,users=data;seed(db,users[0]);common=change("income_adjustment","1000")
    one=saved(db,users[0],"Rent",[common,change("recurring_expense_adjustment","500")]);two=saved(db,users[0],"Salary",[common,common]);three=saved(db,users[0],"Three",[common])
    results=[run(db,users[0],row,key=f"run-key-{row.id}") for row in [one,two,three]]
    before=state(db);count=db.query(ScenarioRun).count()
    def forbidden(*args,**kwargs):raise AssertionError("Comparison must not invoke financial calculations")
    monkeypatch.setattr(q,"calculate",forbidden)
    q.set_status(db,users[0].id,three.id,"archived")
    result=library.compare(db,users[0].id,ScenarioCompareRequest(scenario_ids=[one.id,two.id,three.id]))
    assert [col.result for col in result.columns]==results
    assert [a.shared for a in result.columns[0].assumptions]==[True,False]
    assert [a.shared for a in result.columns[1].assumptions]==[True,False]
    for row in result.metrics:
        for cell,stored in zip(row.cells,results):assert cell.comparison==next(m for m in stored.comparisons if m.metric==row.metric)
    assert state(db)==before and db.query(ScenarioRun).count()==count


def test_missing_stale_and_insufficient_states_are_not_zero(data):
    db,users=data;one=saved(db,users[0]);two=saved(db,users[0]);run(db,users[0],one)
    missing=library.compare(db,users[0].id,ScenarioCompareRequest(scenario_ids=[one.id,two.id]))
    assert "missing_results" in missing.warnings and missing.columns[1].result is None
    assert all(row.cells[1].comparison is None and row.cells[1].status=="insufficient_data" for row in missing.metrics)
    assert next(row for row in missing.metrics if row.metric=="monthly_income").cells[0].comparison.scenario_value is None
    run(db,users[0],two,key="second-run")
    q.replace_changes(db,users[0].id,one.id,ChangesRequest(changes=[change("income_adjustment","100")]))
    stale=library.compare(db,users[0].id,ScenarioCompareRequest(scenario_ids=[one.id,two.id]))
    assert "stale_results" in stale.warnings and stale.columns[0].result is None
    assert stale.columns[0].scenario.result_revision!=stale.columns[0].scenario.revision


def test_versions_reject_incompatible_but_expose_uniform_historical_version(data):
    db,users=data;one=saved(db,users[0]);two=saved(db,users[0]);run(db,users[0],one);run(db,users[0],two,key="second-run")
    rows=db.query(ScenarioRun).order_by(ScenarioRun.id).all();rows[0].calculation_version="historical-v0";db.commit()
    with pytest.raises(HTTPException) as exc:library.compare(db,users[0].id,ScenarioCompareRequest(scenario_ids=[one.id,two.id]))
    assert exc.value.status_code==409


def test_baseline_date_and_horizon_differences_are_explicit(data):
    db,users=data;seed(db,users[0]);one=saved(db,users[0]);two=saved(db,users[0]);run(db,users[0],one,horizon_days=30);run(db,users[0],two,key="other-horizon",horizon_days=90)
    result=library.compare(db,users[0].id,ScenarioCompareRequest(scenario_ids=[one.id,two.id]))
    assert "different_baselines" in result.warnings and "different_horizons" in result.warnings


@pytest.mark.parametrize("ids",[[1],[1,2,3,4,5,6],[1,1],[0,1]])
def test_compare_bounds(ids):
    with pytest.raises(ValidationError):ScenarioCompareRequest(scenario_ids=ids)


def test_api_tenant_isolation_and_validation(data):
    db,users=data;row=saved(db,users[0]);other=saved(db,users[1]);app.dependency_overrides[get_db]=lambda:db
    try:
        with TestClient(app) as client:
            assert client.post("/finance/scenarios/compare",json={"scenario_ids":[row.id,other.id]}).status_code==401
            app.dependency_overrides[get_current_user]=lambda:users[1]
            for action in ["duplicate","restore","archive","save"]:assert client.post(f"/finance/scenarios/{row.id}/{action}").status_code==404
            assert client.patch(f"/finance/scenarios/{row.id}",json={"name":"Mine"}).status_code==404
            assert client.post("/finance/scenarios/compare",json={"scenario_ids":[other.id,row.id]}).status_code==404
            assert client.get(f"/finance/scenarios/{row.id}").status_code==404
            assert client.get("/finance/scenarios?status=all").json()["total"]==1
            assert client.get("/finance/scenarios?limit=51").status_code==422
            assert client.get("/finance/scenarios?offset=-1").status_code==422
            assert client.get("/finance/scenarios?status=invalid").status_code==422
            assert client.patch(f"/finance/scenarios/{other.id}",json={"owner_id":users[0].id}).status_code==422
            assert client.post("/finance/scenarios/compare",json={"scenario_ids":[other.id]}).status_code==422
    finally:app.dependency_overrides.clear()


def test_library_queries_are_batched(data):
    db,users=data
    for i in range(12):saved(db,users[0],str(i))
    statements=[]
    def record(conn,cursor,statement,*args):
        if statement.lstrip().upper().startswith("SELECT"):statements.append(statement)
    event.listen(db.get_bind(),"before_cursor_execute",record)
    try:
        library.listing(db,users[0].id,limit=1);small=len(statements);statements.clear()
        library.listing(db,users[0].id,limit=20);assert len(statements)==small
    finally:event.remove(db.get_bind(),"before_cursor_execute",record)
