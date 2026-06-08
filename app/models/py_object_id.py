from typing import Annotated
from typing import Any

from bson import ObjectId
from pydantic import PlainSerializer
from pydantic import PlainValidator
from pydantic import WithJsonSchema


def _validate(value: Any) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValueError("Invalid ObjectId")


# ObjectId for Pydantic v2: parsed from str/ObjectId, serialized to str,
# rendered as a string in OpenAPI.
PyObjectId = Annotated[
    ObjectId,
    PlainValidator(_validate),
    PlainSerializer(str, return_type=str),
    WithJsonSchema({"type": "string"}),
]
