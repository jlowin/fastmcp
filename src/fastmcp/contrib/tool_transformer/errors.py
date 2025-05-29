class TransformedToolError(Exception):
    """An error that occurs when a tool is transformed."""

    def __init__(self, message: str):
        super().__init__(message)


class ToolParameterOverrideError(TransformedToolError):
    """An error that occurs when a parameter override is invalid."""

    def __init__(self, parameter_name: str):
        super().__init__(f"Parameter {parameter_name} not found in tool.")


class ToolParameterNotFoundError(TransformedToolError):
    """An error that occurs when a parameter is not found in the schema."""

    def __init__(self, parameter_name: str):
        super().__init__(f"Parameter {parameter_name} not found in tool.")


class ToolParameterAlreadyExistsError(TransformedToolError):
    """An error that occurs when a parameter already exists in the schema."""

    def __init__(self, parameter_name: str):
        super().__init__(f"Parameter {parameter_name} already exists in schema.")
