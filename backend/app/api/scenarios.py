"""Authenticated, owner-scoped scenario workspace endpoints."""
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.scenarios import ScenarioCreate, ChangesRequest, SimulationRequest, ScenarioRead, ScenarioResult, MetricComparison
from app.schemas.scenarios import ScenarioLibraryPage, ScenarioMetadataUpdate, ScenarioCompareRequest, ScenarioLibraryComparison
from app.services.finance import scenario_library as library
from app.api.goal_planning import mutate
from app.services.finance import scenarios as service
router=APIRouter(prefix="/finance/scenarios",tags=["scenarios"])

@router.get("",response_model=ScenarioLibraryPage)
def listing(status:Literal["draft","saved","archived","active","all"]="saved",search:str=Query("",max_length=120),limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0),current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return library.listing(db,current.id,status=status,search=search,limit=limit,offset=offset)

@router.post("/compare",response_model=ScenarioLibraryComparison)
def compare(payload:ScenarioCompareRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:library.compare(db,current.id,payload))

@router.post("",response_model=ScenarioRead)
def create(payload:ScenarioCreate,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.create(db,current.id,payload))

@router.get("/baseline",response_model=ScenarioResult)
def baseline(schedules_confirmed:bool=False,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.calculate(db,current.id,0,[],SimulationRequest(idempotency_key="baseline-view",schedules_confirmed=schedules_confirmed))[0]

@router.get("/{scenario_id}",response_model=ScenarioRead)
def get(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.read(db,service.owned(db,current.id,scenario_id))

@router.post("/{scenario_id}/changes",response_model=ScenarioRead)
@router.patch("/{scenario_id}/changes",response_model=ScenarioRead)
def changes(scenario_id:int,payload:ChangesRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.replace_changes(db,current.id,scenario_id,payload))

@router.post("/{scenario_id}/simulate",response_model=ScenarioResult)
def simulate(scenario_id:int,payload:SimulationRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.simulate(db,current.id,scenario_id,payload))

@router.get("/{scenario_id}/result",response_model=ScenarioResult)
def result(scenario_id:int,run_id:int|None=None,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.result_for(db,current.id,scenario_id,run_id)

@router.get("/{scenario_id}/comparison",response_model=list[MetricComparison])
def comparison(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.result_for(db,current.id,scenario_id).comparisons

@router.post("/{scenario_id}/save",response_model=ScenarioRead)
def save(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.set_status(db,current.id,scenario_id,"saved"))

@router.post("/{scenario_id}/archive",response_model=ScenarioRead)
def archive(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.set_status(db,current.id,scenario_id,"archived"))


@router.patch("/{scenario_id}",response_model=ScenarioRead)
def rename(scenario_id:int,payload:ScenarioMetadataUpdate,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:library.update_metadata(db,current.id,scenario_id,payload))

@router.post("/{scenario_id}/duplicate",response_model=ScenarioRead)
def duplicate(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:library.duplicate(db,current.id,scenario_id))

@router.post("/{scenario_id}/restore",response_model=ScenarioRead)
def restore(scenario_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:library.restore(db,current.id,scenario_id))
