# Icon System Usage Examples

This document provides practical examples of using the TAP icon system.

## Example 1: Plugin with Named Icons

The simplest approach - reference icon library names:

```python
# my_plugin/apps.py
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
            "slug": "database",
            "display_name": "Database",
            "icon": "named:fa-database",  # Another Font Awesome icon
            "description": "A database system",
        },
    ]
```

Usage in templates:
```django
<i class="fa {{ entity_type.get_icon_url }}"></i>
```

## Example 2: Plugin with Static Icons

Provide custom SVG icons bundled with your plugin:

**File structure:**
```
my_plugin/
├── apps.py
├── models.py
└── static/
    └── my_plugin/
        └── icons/
            ├── custom-server.svg
            └── custom-database.svg
```

**Plugin configuration:**
```python
# my_plugin/apps.py
class MyPluginConfig(TapPluginConfig):
    name = "my_plugin"
    verbose_name = "My Plugin"

    entity_types = [
        {
            "slug": "custom_server",
            "display_name": "Custom Server",
            "icon": "static:my_plugin/icons/custom-server.svg",
            "description": "Server with custom icon",
        },
    ]
```

**Usage in templates:**
```django
{% load static %}
<img src="{% static entity_type.icon_data.value %}" alt="{{ entity_type.display_name }}">
```

## Example 3: Programmatic Icon Management

Managing icons through code:

```python
from tap_core.models import EntityType
from tap_core.icon_types import IconReference

# Get an entity type
entity_type = EntityType.objects.get(slug="server")

# Read the current icon
icon_ref = entity_type.get_icon_reference()
print(f"Current icon: {icon_ref.icon_type} - {icon_ref.value}")

# Change to a different named icon
new_icon = IconReference.named("fa-cloud-server")
entity_type.set_icon_reference(new_icon)
entity_type.save()

# Or set a static icon
static_icon = IconReference.static(
    "my_plugin/icons/special.svg",
    plugin_name="my_plugin"
)
entity_type.set_icon_reference(static_icon)
entity_type.save()
```

## Example 4: Uploaded Icons (Admin/API)

For user-uploaded icons (requires authentication):

```python
from django.core.files.storage import default_storage
from tap_core.icon_types import IconReference

# Save uploaded file (in a view/form handler)
def handle_icon_upload(uploaded_file, user):
    # Save to media/icons/
    file_path = default_storage.save(
        f'icons/user_{user.id}/{uploaded_file.name}',
        uploaded_file
    )
    
    # Create icon reference
    icon_ref = IconReference.uploaded(
        file_path,
        uploader_id=user.id
    )
    
    return icon_ref

# Use the uploaded icon
entity_type.set_icon_reference(icon_ref)
entity_type.save()
```

Access URL: `/media/icons/user_123/icon.svg` (requires login)

## Example 5: Backward Compatibility

Old code with plain strings still works:

```python
# Old plugin definition (still works!)
entity_types = [
    {
        "slug": "legacy",
        "display_name": "Legacy",
        "icon": "fa-legacy",  # No prefix = named icon
    }
]

# Gets parsed as:
IconReference(icon_type=IconType.NAMED, value="fa-legacy")
```

## Example 6: Mixed Icon Types

Using different icon types in the same plugin:

```python
class MixedPluginConfig(TapPluginConfig):
    name = "mixed_plugin"
    verbose_name = "Mixed Plugin"

    entity_types = [
        # Standard icon library
        {
            "slug": "standard",
            "display_name": "Standard",
            "icon": "named:fa-check",
        },
        # Custom bundled icon
        {
            "slug": "special",
            "display_name": "Special",
            "icon": "static:mixed_plugin/icons/special.svg",
        },
        # No icon (will show default)
        {
            "slug": "plain",
            "display_name": "Plain",
            "icon": "",
        },
    ]
```

## Example 7: Django Admin Integration

Register entity types in admin with icon display:

```python
# my_plugin/admin.py
from django.contrib import admin
from tap_core.models import EntityType

@admin.register(EntityType)
class EntityTypeAdmin(admin.ModelAdmin):
    list_display = ['slug', 'display_name', 'icon_preview', 'plugin_name']
    
    def icon_preview(self, obj):
        icon_ref = obj.get_icon_reference()
        if not icon_ref:
            return "-"
        
        if icon_ref.icon_type == IconType.NAMED:
            return f'<i class="fa {icon_ref.value}"></i>'
        else:
            url = obj.get_icon_url()
            return f'<img src="{url}" width="24" height="24">'
    
    icon_preview.allow_tags = True
    icon_preview.short_description = "Icon"
```

## Example 8: API Usage (Django Ninja)

Expose icons through API:

```python
# my_plugin/api.py
from ninja import Router
from tap_core.models import EntityType

router = Router()

@router.get("/entity-types")
def list_entity_types(request):
    types = EntityType.objects.all()
    return [
        {
            "slug": et.slug,
            "display_name": et.display_name,
            "icon": {
                "type": et.icon_data.get("type") if et.icon_data else "named",
                "value": et.icon_data.get("value") if et.icon_data else "",
                "url": et.get_icon_url(),
            },
        }
        for et in types
    ]
```

## Best Practices

1. **Use named icons for standard types**: They're lightweight and cached
2. **Use static icons for plugin-specific types**: Version-controlled and bundled
3. **Reserve uploaded icons for user customization**: Runtime flexibility
4. **Always provide alt text**: For accessibility
5. **Use SVG format for static icons**: Scalable and small file size
6. **Namespace your static paths**: `my_plugin/icons/` not just `icons/`

## Security Notes

- Named icons: No security concerns (just CSS classes)
- Static icons: Served through Django's static files (public)
- Uploaded icons: Require authentication, path-traversal protected
- Always validate uploaded file types and sizes before saving
