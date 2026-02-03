
from datetime import date
from pydantic import BaseModel, Field, field_validator, ConfigDict, field_serializer, ValidationError
from fastapi import UploadFile, Form, File, HTTPException, status

from database.models.accounts import GenderEnum
from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date,
)


class ProfileCreateSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_names(cls, value: str):
        validate_name(value)
        return value

    @field_validator("gender")
    @classmethod
    def validate_gender_field(cls, value: str):
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth(cls, value: date):
        validate_birth_date(value)
        return value

    @field_validator("info")
    @classmethod
    def validate_info(cls, value: str):
        if not value.strip():
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return value

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, value: UploadFile):
        validate_image(value)
        value.file.seek(0)
        return value

    @classmethod
    def as_form(
            cls,
            first_name: str = Form(...),
            last_name: str = Form(...),
            gender: str = Form(...),
            date_of_birth: date = Form(...),
            info: str = Form(...),
            avatar: UploadFile = File(...),
    ):
        try:
            return cls(
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                date_of_birth=date_of_birth,
                info=info,
                avatar=avatar,
            )
        except ValidationError as e:
            errors = []

            for err in e.errors():

                if "ctx" in err and "error" in err["ctx"]:
                    err["ctx"]["error"] = str(err["ctx"]["error"])

                if "input" in err:
                    err["input"] = str(err["input"])

                errors.append(err)

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str

    model_config = ConfigDict(from_attributes=True)
