class UamlError(Exception):
    """A stable diagnostic code without echoing potentially sensitive input."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def diagnostic(self) -> dict:
        return {"code": self.code, "message": self.message}
