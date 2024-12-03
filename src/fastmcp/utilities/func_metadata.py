import inspect
from collections.abc import Callable, Sequence
from typing import (
    Annotated,
    Any,
    Dict,
    ForwardRef,
)
from pydantic import Field
from fastmcp.exceptions import InvalidSignature
from pydantic._internal._typing_extra import try_eval_type
import json
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic import ConfigDict, create_model
from pydantic import WithJsonSchema
from pydantic_core import PydanticUndefined
from fastmcp.utilities.logging import get_logger


logger = get_logger(__name__)


class ArgModelBase(BaseModel):
    """A model representing the arguments to a function."""

    def model_dump_one_level(self) -> dict[str, Any]:
        """Return a dict of the model's fields, one level deep.

        That is, sub-models etc are not dumped - they are kept as pydantic models.
        """
        kwargs: dict[str, Any] = {}
        for field_name in self.model_fields.keys():
            kwargs[field_name] = getattr(self, field_name)
        return kwargs

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


class FuncMetadata(BaseModel):
    arg_model: Annotated[type[ArgModelBase], WithJsonSchema(None)]
    # We can add things in the future like
    #  - Maybe some args are excluded from attempting to parse from JSON
    #  - Maybe some args are special (like context) for dependency injection

    async def call_fn_with_arg_validation(
        self,
        fn: Callable,
        fn_is_async: bool,
        arguments_to_validate: dict[str, Any],
        arguments_to_pass_directly: dict[str, Any] | None,
    ) -> Any:
        """Call the given function with arguments validated and injected.

        Arguments are first attempted to be parsed from JSON, then validated against
        the argument model, before being passed to the function.
        """
        arguments_pre_parsed = self.pre_parse_json(arguments_to_validate)
        arguments_parsed_model = self.arg_model.model_validate(arguments_pre_parsed)
        arguments_parsed_dict = arguments_parsed_model.model_dump_one_level()

        arguments_parsed_dict |= arguments_to_pass_directly or {}

        if fn_is_async:
            return await fn(**arguments_parsed_dict)
        return fn(**arguments_parsed_dict)

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        """Pre-parse data from JSON.

        Return a dict with same keys as input but with values parsed from JSON
        if appropriate.

        This is to handle cases like `["a", "b", "c"]` being passed in as JSON inside
        a string rather than an actual list. Claude desktop is prone to this - in fact
        it seems incapable of NOT doing this. For sub-models, it tends to pass
        dicts (JSON objects) as JSON strings, which can be pre-parsed here.
        """
        new_data = data.copy()  # Shallow copy
        for field_name, field_info in self.arg_model.model_fields.items():
            if field_name not in data.keys():
                continue
            if isinstance(data[field_name], str):
                try:
                    pre_parsed = json.loads(data[field_name])
                except json.JSONDecodeError:
                    continue  # Not JSON - skip
                if isinstance(pre_parsed, str):
                    # This is likely that the raw value is e.g. `"hello"` which we
                    # Should really be parsed as '"hello"' in Python - but if we parse
                    # it as JSON it'll turn into just 'hello'. So we skip it.
                    continue
                new_data[field_name] = pre_parsed
        assert new_data.keys() == data.keys()
        return new_data

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


def func_metadata(func: Callable, skip_names: Sequence[str] = ()) -> FuncMetadata:
    """Given a function, return metadata including a pydantic model representing its signature.

    The use case for this is
    ```
    meta = func_to_pyd(func)
    validated_args = meta.arg_model.model_validate(some_raw_data_dict)
    return func(**validated_args.model_dump_one_level())
    ```

    **critically** it also provides pre-parse helper to attempt to parse things from JSON.

    Args:
        func: The function to convert to a pydantic model
        skip_names: A list of parameter names to skip. These will not be included in
            the model.
    Returns:
        A pydantic model representing the function's signature.
    """
    sig = _get_typed_signature(func)
    params = sig.parameters
    dynamic_pydantic_model_params: dict[str, Any] = {}
    for param in params.values():
        if param.name.startswith("_"):
            raise InvalidSignature(
                f"Parameter {param.name} of {func.__name__} may not start with an underscore"
            )
        if param.name in skip_names:
            continue
        annotation = param.annotation

        # `x: None` / `x: None = None`
        if annotation is None:
            annotation = Annotated[
                None,
                Field(
                    default=param.default
                    if param.default is not inspect.Parameter.empty
                    else PydanticUndefined
                ),
            ]

        # Untyped field
        if annotation is inspect.Parameter.empty:
            annotation = Annotated[
                Any,
                Field(),
                # 🤷
                WithJsonSchema({"title": param.name, "type": "string"}),
            ]

        field_info = FieldInfo.from_annotated_attribute(
            annotation,
            param.default
            if param.default is not inspect.Parameter.empty
            else PydanticUndefined,
        )
        dynamic_pydantic_model_params[param.name] = (field_info.annotation, field_info)
        continue

    arguments_model = create_model(
        f"{func.__name__}Arguments",
        **dynamic_pydantic_model_params,
        __base__=ArgModelBase,
    )
    resp = FuncMetadata(arg_model=arguments_model)
    return resp


def _get_typed_annotation(annotation: Any, globalns: Dict[str, Any]) -> Any:
    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        annotation, status = try_eval_type(annotation, globalns, globalns)

        # This check and raise could perhaps be skipped, and we (FastMCP) just call
        # model_rebuild right before using it 🤷
        if status is False:
            raise InvalidSignature(f"Unable to evaluate type annotation {annotation}")

    return annotation


def _get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    """Get function signature while evaluating forward references"""
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=_get_typed_annotation(param.annotation, globalns),
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(typed_params)
    return typed_signature
