from pydantic import BaseModel, ConfigDict


class PrincipalRead(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"subject": "auth0|abc123", "email": "user@example.com", "roles": ["user"]}
            ]
        }
    )

    subject: str
    email: str | None
    roles: list[str]
