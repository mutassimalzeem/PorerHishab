"""FastAPI router for the AI-15S financial coach orchestration (AI-15S-G / AI-15S-K).

Orchestrates deterministic intent routing, evidence assembly, LLM generation,
deterministic response validation, and message persistence with strict tenant
isolation and failure safety.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.financial_coach import CoachTurn, CoachMessage
from app.models.user import User
from app.schemas.financial_coach import (
    CoachConversationDetail,
    CoachConversationPage,
    CoachConversationSummary,
    CoachMessageRead,
    CoachRequest,
    CoachResponse,
    CoachTurnRead,
)
from app.services.finance.financial_coach_evidence import assemble_financial_evidence
from app.services.finance.financial_coach_generator import (
    DeterministicFallbackGenerator,
    FinancialCoachGenerator,
)
from app.services.finance.financial_coach_persistence import (
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_recent_history_context,
    list_conversations,
    claim_turn,
    complete_turn,
    fail_turn,
    get_turn,
    turn_view,
)
from app.services.finance.financial_coach_router import (
    CoachIntent,
    route_financial_coach_question,
)
from app.services.finance.financial_coach_validator import validate_coach_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["financial-coach"])


@router.post("/ask", response_model=CoachResponse)
def ask_financial_coach(
    payload: CoachRequest,
    language: str = Query("en", pattern="^(en|bn)$"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoachResponse:
    """Primary financial coach endpoint.

    Orchestrates routing, evidence assembly, generation, validation, and persistence.
    Persists a durable receipt, then completes or exposes a recoverable turn.
    """
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty.",
        )

    conv_id: str | None = None
    turn = None
    lease_token = None
    try:
        turn, lease_token = claim_turn(db, current.id, payload, language)
        conv_id = turn.conversation_id
        request_id = turn.request_id
        if lease_token is None:
            return CoachResponse.model_validate(turn.response_json)

        # 3. Deterministic intent routing (AI-15S-B)
        try:
            route = route_financial_coach_question(message_text)
        except Exception as exc:
            logger.warning("Coach routing failed: %s", type(exc).__name__)
            route = route_financial_coach_question("unknown question")

        # 4. Deterministic evidence assembly (AI-15S-C)
        evidence_package = assemble_financial_evidence(
            db=db,
            user_id=current.id,
            route=route,
            question=message_text,
            purchase_amount=route.extracted_amount,
            schedules_confirmed=payload.schedules_confirmed,
        )

        # 5. Fast-path: clarification required or unknown intent
        if evidence_package.requires_clarification or evidence_package.intent == CoachIntent.UNKNOWN:
            response = DeterministicFallbackGenerator.generate(
                evidence_package,
                question=message_text,
                language=language,
            )
            response.conversation_id = conv_id
            db.commit()
            return complete_turn(db, current.id, request_id, lease_token, response)

        # 6. Retrieve recent history for context (AI-15S-F)
        history = get_recent_history_context(db, current.id, conv_id, limit=6)
        # Release the read transaction before potentially slow optional inference.
        db.commit()
        if history:
            history = [{"role": "system", "content": "Historical conversation only. Use current server evidence for all financial facts."}, *history]

        # 7. Structured generation (AI-15S-D)
        generator = FinancialCoachGenerator(language=language)
        unvalidated_response = generator.generate_response(
            package=evidence_package,
            question=message_text,
            conversation_history=history,
            conversation_id=conv_id,
        )

        # 8. Deterministic evidence-grounded validation (AI-15S-E / AI-15S-K)
        validated_response, report = validate_coach_response(
            response=unvalidated_response,
            package=evidence_package,
            language=language,
        )
        validated_response.conversation_id = conv_id

        if report.repaired:
            logger.info(
                "Coach response was repaired for user %s: dropped %d claims, %d actions.",
                current.id,
                report.dropped_claims_count,
                report.dropped_actions_count,
            )

        # 9. Persist assistant response with structured details
        return complete_turn(db, current.id, request_id, lease_token, validated_response)

    except HTTPException:
        db.rollback()
        if turn is not None and lease_token:
            try:
                fail_turn(db, current.id, request_id, lease_token)
            except Exception:
                db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Financial coach execution error for user %s, conv %s: %s",
            current.id,
            conv_id or "unknown",
            type(exc).__name__,
        )
        if turn is not None and lease_token:
            try:
                fail_turn(db, current.id, request_id, lease_token)
            except Exception:
                db.rollback()  # If storage is down, the lease eventually permits recovery.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your financial coaching request.",
        )


@router.get("/conversations", response_model=CoachConversationPage)
def get_user_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoachConversationPage:
    """List authenticated user's coaching conversations with pagination."""
    items, total = list_conversations(db, current.id, limit=limit, offset=offset)
    summaries = [
        CoachConversationSummary(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in items
    ]
    return CoachConversationPage(
        items=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=CoachConversationDetail)
def get_conversation_detail(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=200),
    before_id: int | None = Query(None, ge=1),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoachConversationDetail:
    """Retrieve an owned conversation and its messages."""
    conv = get_conversation(db, current.id, conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    messages = get_conversation_messages(db, current.id, conversation_id, limit=limit, before_id=before_id)
    turns = {t.request_id: t for t in db.query(CoachTurn).filter_by(user_id=current.id, conversation_id=conversation_id).filter(
        CoachTurn.request_id.in_([m.request_id for m in messages if m.request_id])).all()}
    latest_id = db.query(func.max(CoachTurn.id)).filter_by(user_id=current.id, conversation_id=conversation_id).scalar()
    views = {key: turn_view(db, current.id, turn, latest_id=latest_id) for key, turn in turns.items()}
    msg_reads = [
        CoachMessageRead(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            summary=m.summary,
            claims_json=m.claims_json,
            actions_json=m.actions_json,
            evidence_ids_json=m.evidence_ids_json,
            evidence_json=m.evidence_json,
            warnings_json=m.warnings_json,
            limitations_json=m.limitations_json,
            created_at=m.created_at,
            request_id=m.request_id,
            turn_status=views[m.request_id].status if m.request_id in views else None,
            retry_safe=views[m.request_id].retry_safe if m.role == "user" and m.request_id in views else False,
            response=CoachResponse.model_validate(turns[m.request_id].response_json) if m.role == "assistant" and m.request_id in turns and turns[m.request_id].state == "completed" else None,
        )
        for m in messages
    ]

    return CoachConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=msg_reads,
        has_more=bool(messages and db.query(CoachMessage.id).filter_by(user_id=current.id, conversation_id=conversation_id).filter(CoachMessage.id < messages[0].id).first()),
        next_before_id=messages[0].id if messages else None,
    )


@router.get("/requests/{request_id}", response_model=CoachTurnRead)
def get_request_status(request_id: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    turn = get_turn(db, current.id, request_id)
    if turn is None:
        raise HTTPException(404, "Coaching request not found.")
    return turn_view(db, current.id, turn)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: str,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a conversation and its messages."""
    try:
        deleted = delete_conversation(db, current.id, conversation_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to delete conversation %s for user %s: %s",
            conversation_id,
            current.id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the conversation.",
        )
