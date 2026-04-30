import logging


security_log = logging.getLogger("security")


def get_client_ip(request):
    if request is None:
        return "unknown"

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "unknown")
