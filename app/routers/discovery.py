import json
import subprocess
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DiscoveryJob, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/discovery", tags=["discovery"])
templates = get_templates()


