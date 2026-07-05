from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Incident
from app.services.rca_service import analyze_pagerank
from app.template_utils import get_templates

router = APIRouter(prefix="/pagerank-rca", tags=["pagerank_rca"])
templates = get_templates()


