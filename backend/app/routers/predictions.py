from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Prediction
from app.schemas import PredictionOut

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/{prediction_id}", response_model=PredictionOut)
def get_prediction(prediction_id: int, db: Session = Depends(get_db)):
    prediction = (
        db.query(Prediction)
        .filter(Prediction.id == prediction_id)
        .options(
            selectinload(Prediction.outcome),
            selectinload(Prediction.statement),
        )
        .first()
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction
