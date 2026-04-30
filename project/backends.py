from axes.backends import AxesStandaloneBackend


class SafeAxesStandaloneBackend(AxesStandaloneBackend):
    def authenticate(self, request=None, username=None, password=None, **kwargs):
        if request is None:
            return None

        return super().authenticate(
            request=request,
            username=username,
            password=password,
            **kwargs,
        )
