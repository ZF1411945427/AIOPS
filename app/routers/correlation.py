import math
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import MetricRecord

router = APIRouter(prefix="/correlation", tags=["correlation"])
templates = get_templates()


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(a * b for a, b in zip(xs, ys))
    sum_xx = sum(a * a for a in xs)
    sum_yy = sum(b * b for b in ys)
    denom = math.sqrt((n * sum_xx - sum_x * sum_x) * (n * sum_yy - sum_y * sum_y))
    if denom == 0:
        return 0
    return (n * sum_xy - sum_x * sum_y) / denom


