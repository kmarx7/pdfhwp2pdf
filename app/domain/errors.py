class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422,
                 details: dict | None = None, suggestion: str = "파일을 확인한 뒤 다시 시도하세요."):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        self.suggestion = suggestion

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "details": self.details, "suggestion": self.suggestion,
                "retryable": self.code in {"QUEUE_FULL", "INTERRUPTED"}}
