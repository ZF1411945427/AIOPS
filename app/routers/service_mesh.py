import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ServiceMeshConfig
from app.template_utils import get_templates

router = APIRouter(prefix="/service-mesh", tags=["service-mesh"])
templates = get_templates()


