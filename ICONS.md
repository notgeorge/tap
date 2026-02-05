# Icon System in TAP

## Overview

TAP uses a flexible, secure icon system that supports three types of icons:

1. **Named Icons** - References to icon libraries (Font Awesome, Material Icons, etc.)
2. **Static Icons** - Plugin-provided icon files served from static directories
3. **Uploaded Icons** - User-uploaded icon files with authentication and permission checks

## Architecture

### Data Model

The icon system uses a dual-field approach for backward compatibility:

- `icon` (CharField): Simple string representation (e.g., "named:fa-server")
- `icon_data` (JSONField): Structured data with type, value, and metadata

The `EntityType` model provides helper methods:
- `get_icon_reference()` - Returns an `IconReference` object
- `set_icon_reference(icon_ref)` - Sets icon from an `IconReference` object
- `get_icon_url()` - Returns the URL to access the icon

### Icon Types

#### Named Icons

Named icons are references to CSS icon libraries. They don't require file storage.

**Example:**
```python
from tap_core.icon_types import IconReference

icon = IconReference.named("fa-server")
# Stored as: "named:fa-server"
# URL: "fa-server" (used in CSS classes)
```

**In plugins:**
```python
entity_types = [
    {
        "slug": "server",
        "display_name": "Server",
        "icon": "named:fa-server",
    }
]
```

#### Static Icons

Static icons are files provided by plugins in their static directories. They're served by Django's static file system.

**Example:**
```python
icon = IconReference.static(
    "my_plugin/icons/custom.svg",
    plugin_name="my_plugin"
)
# Stored as: "static:my_plugin/icons/custom.svg"
# URL: "/static/my_plugin/icons/custom.svg"
```

**Plugin structure:**
```
my_plugin/
├── apps.py
├── models.py
└── static/
    └── my_plugin/
        └── icons/
            └── custom.svg
```

**In plugins:**
```python
entity_types = [
    {
        "slug": "custom_type",
        "display_name": "Custom Type",
        "icon": "static:my_plugin/icons/custom.svg",
    }
]
```

#### Uploaded Icons

Uploaded icons are user-provided files stored in `MEDIA_ROOT/icons/`. They require authentication to access.

**Example:**
```python
icon = IconReference.uploaded(
    "user_uploads/icon.svg",
    uploader_id=123
)
# Stored as: "uploaded:user_uploads/icon.svg"
# URL: "/media/icons/user_uploads/icon.svg" (requires authentication)
```

**Security:**
- Served through Django view (`serve_icon`) with authentication check
- Path traversal protection prevents accessing files outside icon directory
- Can be extended with per-icon permission checks

## Usage

### In Plugins

When defining entity types, specify the icon with a type prefix:

```python
from tap_plugins.base import TapPluginConfig

class MyPluginConfig(TapPluginConfig):
    name = "my_plugin"
    verbose_name = "My Plugin"

    entity_types = [
        {
            "slug": "server",
            "display_name": "Server",
            "icon": "named:fa-server",  # Font Awesome icon
            "description": "A physical or virtual server",
        },
        {
            "slug": "custom",
            "display_name": "Custom",
            "icon": "static:my_plugin/icons/custom.svg",  # Plugin static file
            "description": "A custom entity type",
        },
    ]
```

### In Code

Working with icons programmatically:

```python
from tap_core.models import EntityType
from tap_core.icon_types import IconReference

# Get entity type
entity_type = EntityType.objects.get(slug="server")

# Get icon reference
icon_ref = entity_type.get_icon_reference()
if icon_ref:
    print(f"Icon type: {icon_ref.icon_type}")
    print(f"Icon value: {icon_ref.value}")
    print(f"Icon URL: {icon_ref.get_url()}")

# Set a new icon
new_icon = IconReference.named("fa-database")
entity_type.set_icon_reference(new_icon)
entity_type.save()

# Or use the helper method
icon_url = entity_type.get_icon_url()
```

### In Templates

Using icons in Django templates:

```django
{% load static %}

{# Named icon (Font Awesome) #}
<i class="{{ entity_type.get_icon_url }}"></i>

{# Static icon (SVG) #}
<img src="{% static entity_type.icon_data.value %}" alt="{{ entity_type.display_name }}">

{# Uploaded icon (requires authentication) #}
<img src="{{ entity_type.get_icon_url }}" alt="{{ entity_type.display_name }}">
```

## Security Considerations

### Uploaded Icon Security

Uploaded icons are served through the `serve_icon` view which:

1. **Requires authentication**: Users must be logged in
2. **Prevents path traversal**: Blocks attempts to access files outside `/media/icons/`
3. **Validates file existence**: Returns 404 for non-existent files
4. **Can be extended**: Add per-icon permission checks based on metadata

### Best Practices

1. **Use named icons for built-in types**: They're lightweight and don't require file storage
2. **Use static icons for plugin-specific types**: Bundle them with your plugin
3. **Use uploaded icons sparingly**: They require storage and authentication overhead
4. **Validate uploaded files**: Check file type, size, and content before accepting uploads
5. **Clean up unused uploads**: Implement periodic cleanup of orphaned icon files

## API

### IconReference Class

Located in `tap_core/icon_types.py`:

```python
# Create icon references
icon = IconReference.named("fa-server")
icon = IconReference.static("plugin/icon.svg", plugin_name="my_plugin")
icon = IconReference.uploaded("uploads/icon.svg", uploader_id=123)

# Serialization
dict_data = icon.to_dict()  # For JSONField storage
string_data = icon.to_string()  # For CharField storage

# Deserialization
icon = IconReference.from_dict(dict_data)
icon = IconReference.from_string(string_data)

# Get URL
url = icon.get_url()
```

### EntityType Methods

```python
# Get icon as IconReference object
icon_ref = entity_type.get_icon_reference()

# Set icon from IconReference object
entity_type.set_icon_reference(icon_ref)

# Get icon URL directly
url = entity_type.get_icon_url()
```

## Backward Compatibility

The icon system maintains backward compatibility:

1. Existing `icon` CharField continues to work
2. Plain strings without type prefix default to named icons
3. Both `icon` and `icon_data` are updated together
4. `get_icon_reference()` prefers `icon_data` but falls back to `icon`

## Future Enhancements

Potential improvements for future versions:

1. **Icon library management**: UI for selecting from available icon libraries
2. **Icon preview**: Admin interface for previewing icons before selection
3. **Icon validation**: Validate SVG files for security issues
4. **Icon optimization**: Automatic optimization of uploaded SVG files
5. **Per-icon permissions**: Fine-grained access control based on user roles
6. **Icon versioning**: Track changes to uploaded icons over time
