"""FastAPI router for the AI-15S financial coach orchestration (AI-15S-G).

Orchestrates deterministic intent routing, evidence assembly, LLM generation,
deterministic response validation, and message persistence.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.financial_coach import (
    CoachConversationDetail,
    CoachConversationPage,
    CoachConversationSummary,
    CoachMessageRead,
    CoachRequest,
    CoachResponse,
)
from app.services.finance.financial_coach_evidence import assemble_financial_evidence
from app.services.finance.financial_coach_generator import (
    DeterministicFallbackGenerator,
    FinancialCoachGenerator,
)
from app.services.finance.financial_coach_persistence import (
    append_assistant_message,
    append_user_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_recent_history_context,
    list_conversations,
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
    """
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty.",
        )

    # 1. Resolve or create conversation
    conv_id = payload.conversation_id
    if conv_id:
        conv = get_conversation(db, current.id, conv_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )
    else:
        title = message_text[:60] + ("..." if len(message_text) > 60 else "")
        conv = create_conversation(db, current.id, title=title)
        conv_id = conv.id

    # 2. Append user question to persistent conversation
    append_user_message(db, current.id, conv_id, message_text)

    # 3. Deterministic intent routing (AI-15S-B)
    try:
        route = route_financial_coach_question(message_text)
    except Exception as exc:
        logger.warning("Routing error for question: %s", exc)
        route = route_financial_coach_question("unknown question")

    # 4. Deterministic evidence assembly (AI-15S-C)
    evidence_package = assemble_financial_evidence(
        db=db,
        user_id=current.id,
        route=route,
        question=message_text,
        purchase_amount=route.extracted_amount,
    )

    # 5. Fast-path: clarification required or unknown intent
    if evidence_package.requires_clarification or evidence_package.intent == CoachIntent.UNKNOWN:
        response = DeterministicFallbackGenerator.generate(
            evidence_package,
            question=message_text,
            language=language,
        )
        response.conversation_id = conv_id
        append_assistant_message(db, current.id, conv_id, response)
        return response

    # 6. Retrieve recent history for context (AI-15S-F)
    history = get_recent_history_context(db, current.id, conv_id, limit=6)

    # 7. Structured generation (AI-15S-D)
    generator = FinancialCoachGenerator(language=language)
    unvalidated_response = generator.generate_response(
        package=evidence_package,
        question=message_text,
        conversation_history=history,
        conversation_id=conv_id,
    )

    # 8. Deterministic evidence-grounded validation (AI-15S-E)
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

    # 9. Persist assistant response
    append_assistant_message(db, current.id, conv_id, validated_response)

    # 10. Return canonical CoachResponse
    return validated_response


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

    messages = get_conversation_messages(db, current.id, conversation_id, limit=100)
    msg_reads = [
        CoachMessageRead(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            claims_json=m.claims_json,
            actions_json=m.actions_json,
            evidence_ids_json=m.evidence_ids_json,
            created_at=m.created_at,
        )
        for m in messages
    ]

    return CoachConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=msg_reads,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: str,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a conversation and its messages."""
    deleted = delete_conversation(db, current.id, conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
