"""
Icon type system for TAP.

Supports three types of icons:
1. Named icons - references to icon libraries (Font Awesome, Material Icons, etc.)
2. Static icons - plugin-provided icons in static directories
3. Uploaded icons - user-uploaded image files with security controls

Design philosophy:
- Keep it simple and Django-native
- Use existing Django patterns (static files, media files, permissions)
- Make it easy for plugins to provide icons
- Secure by default
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class IconType(Enum):
    """Types of icons supported in TAP."""

    NAMED = "named"  # Reference to icon library (e.g., "fa-server", "material-settings")
    STATIC = "static"  # Plugin-provided static file (e.g., "my_plugin/icons/custom.svg")
    UPLOADED = "uploaded"  # User-uploaded file in MEDIA_ROOT with access control


@dataclass
class IconReference:
    """Structured reference to an icon.

    This replaces the simple CharField with a typed, validated approach.
    Can be serialized to/from dict for JSON storage or as a string for CharField.
    """

    icon_type: IconType
    value: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON field storage."""
        return {
            "type": self.icon_type.value,
            "value": self.value,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IconReference":
        """Deserialize from dict stored in JSON field."""
        return cls(
            icon_type=IconType(data["type"]),
            value=data["value"],
            metadata=data.get("metadata"),
        )

    def to_string(self) -> str:
        """Serialize to string for CharField storage (backward compatibility).

        Format: "type:value" e.g., "named:fa-server", "static:plugin/icon.svg"
        """
        return f"{self.icon_type.value}:{self.value}"

    @classmethod
    def from_string(cls, text: str) -> "IconReference":
        """Deserialize from string in CharField (backward compatibility).

        If no colon, assumes it's a named icon for backward compatibility.
        """
        if ":" in text:
            type_str, value = text.split(":", 1)
            try:
                icon_type = IconType(type_str)
            except ValueError:
                # Invalid type, assume named icon
                icon_type = IconType.NAMED
                value = text
        else:
            # No type prefix, assume named icon
            icon_type = IconType.NAMED
            value = text

        return cls(icon_type=icon_type, value=value)

    @classmethod
    def named(cls, icon_name: str) -> "IconReference":
        """Create a named icon reference (e.g., Font Awesome icon)."""
        return cls(icon_type=IconType.NAMED, value=icon_name)

    @classmethod
    def static(cls, static_path: str, plugin_name: str | None = None) -> "IconReference":
        """Create a static file icon reference.

        Args:
            static_path: Path relative to static directory (e.g., "my_plugin/icons/icon.svg")
            plugin_name: Optional plugin name for metadata tracking
        """
        metadata = {"plugin": plugin_name} if plugin_name else None
        return cls(icon_type=IconType.STATIC, value=static_path, metadata=metadata)

    @classmethod
    def uploaded(cls, file_path: str, uploader_id: int | None = None) -> "IconReference":
        """Create an uploaded file icon reference.

        Args:
            file_path: Path to uploaded file relative to MEDIA_ROOT/icons/
            uploader_id: User ID who uploaded the file (for access control)
        """
        metadata = {"uploader_id": uploader_id} if uploader_id else None
        return cls(icon_type=IconType.UPLOADED, value=file_path, metadata=metadata)

    def get_url(self) -> str:
        """Get the URL to access this icon.

        For named icons, returns the icon identifier to be used with CSS classes.
        For static icons, returns static URL path.
        For uploaded icons, returns media URL path (with security checks in view).
        """
        if self.icon_type == IconType.NAMED:
            # Return the icon name itself - caller will use it in CSS classes
            return self.value
        elif self.icon_type == IconType.STATIC:
            # Return static file URL (Django's static() templatetag handles this)
            return f"/static/{self.value}"
        elif self.icon_type == IconType.UPLOADED:
            # Return media file URL (requires authentication check in view)
            return f"/media/icons/{self.value}"
        return ""

    def __str__(self) -> str:
        """Human-readable representation."""
        return self.to_string()
