from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, UserModel, UserProfileModel
from exceptions import S3FileUploadError

from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from security.interfaces import JWTAuthManagerInterface
from config import get_jwt_auth_manager
from storages.interfaces import S3StorageInterface
from config.dependencies import get_s3_storage_client
from validation import validate_image, validate_name, validate_gender, validate_birth_date
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()


async def get_current_user_payload(
    request: Request,
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
):
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(401, "Authorization header is missing")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            401,
            "Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    token = auth_header.split(" ")[1]

    try:
        return jwt_manager.decode_access_token(token)
    except Exception:
        raise HTTPException(401, "Token has expired.")


async def create_profile(
    db: AsyncSession,
    user_id: int,
    first_name: str,
    last_name: str,
    gender,
    date_of_birth,
    info: str,
    avatar_url: str,
) -> UserProfileModel:

    profile = UserProfileModel(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        date_of_birth=date_of_birth,
        info=info,
        avatar=avatar_url,
    )

    db.add(profile)

    try:
        await db.commit()
        await db.refresh(profile)
    except SQLAlchemyError:
        await db.rollback()
        raise

    return profile


async def get_user_by_id(db: AsyncSession, user_id: int) -> UserModel | None:
    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    return result.scalar_one_or_none()


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_profile(
    user_id: int,
    data: ProfileCreateSchema = Depends(ProfileCreateSchema.as_form),
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    current_user_id = payload.get("user_id")

    avatar_key = f"avatars/{user_id}_avatar.jpg"

    try:
        validate_image(data.avatar)

        data.avatar.file.seek(0)
        file_bytes = await data.avatar.read()

        await s3_client.upload_file(avatar_key, file_bytes)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    except S3FileUploadError:
        raise HTTPException(
            status_code=500,
            detail="Failed to upload avatar. Please try again later."
        )

    current_user = await get_user_by_id(db, current_user_id)

    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="User not found or not active."
        )

    is_admin = current_user.group_id == 3

    if current_user_id != user_id and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to edit this profile."
        )

    stmt = select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    result = await db.execute(stmt)

    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="User already has a profile."
        )

    user = await get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or not active."
        )

    profile = await create_profile(
        db=db,
        user_id=user_id,
        first_name=data.first_name.lower(),
        last_name=data.last_name.lower(),
        gender=data.gender,
        date_of_birth=data.date_of_birth,
        info=data.info.strip(),
        avatar_url=avatar_key,
    )

    profile.avatar = await s3_client.get_file_url(profile.avatar)

    return profile
