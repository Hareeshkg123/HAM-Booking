from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from project.audit import get_client_ip, security_log


@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    security_log.info(
        "auth.login.success user_id=%s username=%s ip=%s",
        getattr(user, "id", None),
        user.get_username(),
        get_client_ip(request),
    )


@receiver(user_logged_out)
def log_user_logged_out(sender, request, user, **kwargs):
    username = user.get_username() if user is not None else "anonymous"
    user_id = getattr(user, "id", None) if user is not None else None
    security_log.info(
        "auth.logout user_id=%s username=%s ip=%s",
        user_id,
        username,
        get_client_ip(request),
    )


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get("username") or credentials.get("email") or "<unknown>"
    path = request.path if request is not None else "<unknown>"
    security_log.warning(
        "auth.login.failed username=%s ip=%s path=%s",
        username,
        get_client_ip(request),
        path,
    )
