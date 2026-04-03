from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Analyst, Statement, SourceType
from app.schemas import StatementOut

router = APIRouter(prefix="/statements", tags=["statements"])


class StatementPaste(BaseModel):
    analyst_id: int
    source_type: str
    content: str
    source_title: Optional[str] = None
    source_url: Optional[str] = None


@router.post("/paste", response_model=StatementOut, status_code=201)
def paste_statement(body: StatementPaste, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == body.analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    try:
        source_type = SourceType(body.source_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source_type: {body.source_type!r}")

    if not body.content or len(body.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Content is too short")

    # Use a unique placeholder URL if none provided
    source_url = body.source_url or f"manual-paste-{analyst.id}-{int(datetime.utcnow().timestamp())}"

    statement = Statement(
        analyst_id=analyst.id,
        source_type=source_type,
        source_url=source_url,
        source_title=body.source_title,
        content=body.content.strip(),
        published_at=None,
        is_processed=False,
    )
    db.add(statement)
    db.commit()
    db.refresh(statement)
    return statement


@router.get("/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: int, db: Session = Depends(get_db)):
    statement = db.query(Statement).filter(Statement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    return statement
