from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Incident
from app.services.pcadr_service import run_pcadr
from app.template_utils import get_templates

router = APIRouter(prefix="/pcadr", tags=["pcadr"])
templates = get_templates()


