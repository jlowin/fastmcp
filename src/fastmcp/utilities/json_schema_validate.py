from jsonschema import validators
from jsonschema._types import is_integer
from jsonschema.validators import Draft202012Validator

from fastmcp.tools.tool import json_schema_uri


def _is_integer(checker, instance):
    if is_integer(checker, instance):
        return True
    if isinstance(instance, str):
        try:
            int(instance)
            return True
        except ValueError:
            pass
    if isinstance(instance, float) and instance.is_integer():
        return True
    return False


llm_type_checker = Draft202012Validator.TYPE_CHECKER.redefine("integer", _is_integer)

llm_validator = validators.extend(
    Draft202012Validator,
    type_checker=llm_type_checker,
)

# Register the custom validator to handle the specific JSON schema URI used by this application.
validators.validates(json_schema_uri)(llm_validator)
