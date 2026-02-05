"""
Secure icon serving views.

Uploaded icons require authentication and permission checks before serving.
This prevents unauthorized access to potentially sensitive icons.
"""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
@login_required
def serve_icon(request: HttpRequest, path: str) -> HttpResponse:
    """Serve an uploaded icon file with authentication and permission checks.

    This view ensures that:
    1. Users are authenticated
    2. Users have permission to view icons (can be extended for per-icon permissions)
    3. Path traversal attacks are prevented
    4. Only files in MEDIA_ROOT/icons/ are served

    Args:
        request: The HTTP request
        path: Relative path to icon file (e.g., "user_uploads/icon.svg")

    Returns:
        FileResponse with the icon file if authorized, 404 otherwise
    """
    # Construct safe file path
    media_root = Path(settings.MEDIA_ROOT)
    icon_dir = media_root / "icons"
    requested_file = icon_dir / path

    # Security checks
    try:
        # Resolve to absolute path and check it's within icon_dir
        # This prevents path traversal attacks like "../../../etc/passwd"
        requested_file = requested_file.resolve()
        if not requested_file.is_relative_to(icon_dir):
            raise ValueError("Path traversal attempt")

        # Check file exists and is a file (not directory)
        if not requested_file.is_file():
            raise Http404("Icon not found")

    except (ValueError, OSError):
        raise Http404("Icon not found")

    # Additional permission checks can be added here
    # For example, checking if user has permission to view this specific icon
    # based on metadata stored in icon_data["metadata"]["uploader_id"]
    # For now, any authenticated user can view any uploaded icon

    # Determine content type
    content_type, _ = mimetypes.guess_type(str(requested_file))
    if content_type is None:
        # Default to generic binary if type cannot be determined
        content_type = "application/octet-stream"

    # Serve the file
    return FileResponse(
        requested_file.open("rb"),
        content_type=content_type,
        as_attachment=False,  # Display inline in browser
    )
