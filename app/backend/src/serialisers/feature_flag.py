from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateFeatureFlagRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    default_enabled: bool = Field(False)
    model_config = ConfigDict(extra="forbid")


class UpdateFeatureFlagRequest(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    default_enabled: Optional[bool] = None
    model_config = ConfigDict(extra="forbid")


class FeatureFlagOverrideSummary(BaseModel):
    organization_id: UUID
    organization_name: str
    enabled: bool


class FeatureFlagResponse(BaseModel):
    id: UUID
    key: str
    name: str
    description: Optional[str]
    default_enabled: bool
    created_time: str
    updated_time: str


class FeatureFlagWithOverridesResponse(BaseModel):
    id: UUID
    key: str
    name: str
    description: Optional[str]
    default_enabled: bool
    created_time: str
    updated_time: str
    overrides: list[FeatureFlagOverrideSummary] = []


class FeatureFlagListResponse(BaseModel):
    items: list[FeatureFlagWithOverridesResponse]
    total: int
    limit: int
    offset: int


class CreateFeatureFlagResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    flag: FeatureFlagResponse


class UpdateFeatureFlagResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    flag: FeatureFlagResponse


class DeleteFeatureFlagResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    flag_id: str


class CreateOverrideRequest(BaseModel):
    organization_id: UUID
    enabled: bool
    model_config = ConfigDict(extra="forbid")


class FeatureFlagOverrideResponse(BaseModel):
    id: UUID
    feature_flag_id: UUID
    organization_id: UUID
    enabled: bool
    created_time: str
    updated_time: str


class FeatureFlagOverrideListResponse(BaseModel):
    items: list[FeatureFlagOverrideResponse]
    total: int
    limit: int
    offset: int


class CreateOverrideResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    override: FeatureFlagOverrideResponse


class DeleteOverrideResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    flag_id: str
    organization_id: str


class ResolvedFeatureFlagsResponse(BaseModel):
    flags: dict[str, bool]
