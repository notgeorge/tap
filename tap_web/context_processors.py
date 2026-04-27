from django.conf import settings


def branding(request):
    return {
        "product_name": getattr(settings, "TAP_PRODUCT_NAME", "TAP"),
        "session_label": getattr(settings, "TAP_SESSION_LABEL", ""),
    }
