"""生成 tabBar 图标 81x81 透明 PNG
未选中 #7A8898，选中 #3B82F6
风格：线性图标(line icon)，描边 4px
"""
from PIL import Image, ImageDraw
import os

SIZE = 81
STROKE = 4
GRAY = (0x7A, 0x88, 0x98, 255)
BLUE = (0x3B, 0x82, 0xF6, 255)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "mobile", "src", "static", "tab")
os.makedirs(OUT, exist_ok=True)


def new_img():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def draw_home(color):
    """首页 - 房子（三角屋顶+方形墙）"""
    img = new_img()
    d = ImageDraw.Draw(img)
    # 屋顶三角
    d.polygon([(40, 14), (12, 40), (68, 40)], outline=color, width=STROKE)
    # 墙体矩形
    d.rectangle([20, 40, 60, 66], outline=color, width=STROKE)
    # 门
    d.rectangle([34, 50, 46, 66], outline=color, width=STROKE)
    return img


def draw_alert(color):
    """告警 - 三角警示牌+感叹号"""
    img = new_img()
    d = ImageDraw.Draw(img)
    # 警示三角
    d.polygon([(40, 12), (10, 66), (70, 66)], outline=color, width=STROKE)
    # 感叹号竖线
    d.line([(40, 32), (40, 52)], fill=color, width=STROKE + 1)
    # 感叹号点
    d.ellipse([37, 58, 43, 64], fill=color)
    return img


def draw_ai(color):
    """AI - 圆形大脑+中心点（火花/星形简化为圆点）"""
    img = new_img()
    d = ImageDraw.Draw(img)
    # 外圆
    d.ellipse([14, 14, 66, 66], outline=color, width=STROKE)
    # 中心点
    d.ellipse([35, 35, 45, 45], fill=color)
    # 四角小点（代表智能辐射）
    for cx, cy in [(27, 27), (53, 27), (27, 53), (53, 53)]:
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=color)
    return img


def draw_mine(color):
    """我的 - 人物头像（圆头+半圆肩）"""
    img = new_img()
    d = ImageDraw.Draw(img)
    # 头
    d.ellipse([28, 14, 52, 38], outline=color, width=STROKE)
    # 肩膀（半圆）
    d.arc([16, 42, 64, 78], start=180, end=360, fill=color, width=STROKE)
    # 底部封口线
    d.line([(16, 60), (64, 60)], fill=color, width=STROKE)
    return img


ICONS = {
    "home": draw_home,
    "alert": draw_alert,
    "ai": draw_ai,
    "mine": draw_mine,
}

for name, fn in ICONS.items():
    fn(GRAY).save(os.path.join(OUT, f"{name}.png"))
    fn(BLUE).save(os.path.join(OUT, f"{name}_on.png"))
    print(f"  {name}.png + {name}_on.png")

print("done,共 8 个图标")
