import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from app.database import get_db
from app.models import MetricRecord, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/hotspot", tags=["hotspot"])
templates = get_templates()


