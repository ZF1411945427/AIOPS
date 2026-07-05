from fastapi import APIRouter, Depends, Request
from app.template_utils import get_templates

from app.database import get_db
from app.services import token_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])
templates = get_templates()


