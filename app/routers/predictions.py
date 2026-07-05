from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.services import prediction_service

router = APIRouter(prefix="/predictions", tags=["predictions"])
templates = get_templates()


