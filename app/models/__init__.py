"""模型层(H2 拆分) - 各域子模块 + 门面聚合, 兼容 `from app.models import X`。"""

from app.database import Base

from app.models.agent import *  # noqa: F401,F403
from app.models.alert import *  # noqa: F401,F403
from app.models.asset import *  # noqa: F401,F403
from app.models.auth import *  # noqa: F401,F403
from app.models.dash import *  # noqa: F401,F403
from app.models.data import *  # noqa: F401,F403
from app.models.deliver import *  # noqa: F401,F403
from app.models.edge import *  # noqa: F401,F403
from app.models.infra import *  # noqa: F401,F403
from app.models.k8s import *  # noqa: F401,F403
from app.models.knowledge import *  # noqa: F401,F403
from app.models.metric import *  # noqa: F401,F403
from app.models.mobile import *  # noqa: F401,F403
from app.models.model import *  # noqa: F401,F403
from app.models.notify import *  # noqa: F401,F403
from app.models.ops import *  # noqa: F401,F403
from app.models.report import *  # noqa: F401,F403
from app.models.skill import *  # noqa: F401,F403
from app.models.sre import *  # noqa: F401,F403
from app.models.system import *  # noqa: F401,F403
from app.models.workflow import *  # noqa: F401,F403

ALL_MODELS = [Base]
