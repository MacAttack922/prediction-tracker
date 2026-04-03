from datetime import datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Analyst, Statement, SourceType

router = APIRouter(prefix="/api/bulk-import", tags=["bulk-import"])

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class BulkImportRequest(BaseModel):
    analyst_id: int
    urls: List[str]
    source_type: str = "website"


class BulkImportResult(BaseModel):
    total: int
    imported: int
    skipped: int
    failed: List[str]


def _fetch_url_content(url: str) -> Optional[str]:
    try:
        with httpx.Client(follow_redirects=True, timeout=15, headers=_HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.find("body")
    if not container:
        return None
    paragraphs = [p.get_text(separator=" ", strip=True) for p in container.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return text if len(text) > 100 else None


@router.post("", response_model=BulkImportResult)
def bulk_import(body: BulkImportRequest, db: Session = Depends(get_db)):
    analyst = db.query(Analyst).filter(Analyst.id == body.analyst_id).first()
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    try:
        source_type = SourceType(body.source_type)
    except ValueError:
        source_type = SourceType.website

    imported = 0
    skipped = 0
    failed: List[str] = []

    for url in body.urls:
        url = url.strip()
        if not url:
            continue

        existing = db.query(Statement).filter(
            Statement.analyst_id == body.analyst_id,
            Statement.source_url == url
        ).first()
        if existing:
            skipped += 1
            continue

        content = _fetch_url_content(url)
        if not content:
            failed.append(url)
            continue

        title = url.split("/")[-1].replace("-", " ").replace("_", " ")[:100]

        stmt = Statement(
            analyst_id=body.analyst_id,
            source_type=source_type,
            source_url=url,
            source_title=title,
            content=content,
            published_at=None,
            is_processed=False,
        )
        try:
            db.add(stmt)
            db.commit()
            imported += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
        except Exception:
            db.rollback()
            failed.append(url)

    return BulkImportResult(total=len(body.urls), imported=imported, skipped=skipped, failed=failed)
