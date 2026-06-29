import mimetypes
from pathlib import Path

from django.http import FileResponse, Http404


FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist'


def _serve_file(file_path):
    if not file_path.exists() or not file_path.is_file():
        raise Http404('Frontend asset not found')
    content_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(open(file_path, 'rb'), content_type=content_type)


def frontend_index(request):
    return _serve_file(FRONTEND_DIST_DIR / 'index.html')


def frontend_asset(request, path):
    safe_path = (FRONTEND_DIST_DIR / path).resolve()
    if FRONTEND_DIST_DIR.resolve() not in safe_path.parents and safe_path != FRONTEND_DIST_DIR.resolve():
        raise Http404('Invalid asset path')
    return _serve_file(safe_path)
