"""Admin serialisers for site message templates (M1). snake_case."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.constants.freespace import AdvisoryType
from src.models.site_message_template import SiteMessageTemplate
from src.services.freespace.templates import ALLOWED_PLACEHOLDERS, DEFAULT_TEMPLATES


class TemplateResponse(BaseModel):
    advisory_type: str
    locale: str
    title: str
    body: str
    default_title: str
    default_body: str
    allowed_placeholders: list[str]

    @classmethod
    def from_row(cls, row: SiteMessageTemplate) -> TemplateResponse:
        advisory_type = AdvisoryType(row.advisory_type)
        default_title, default_body = DEFAULT_TEMPLATES[advisory_type]
        return cls(
            advisory_type=row.advisory_type,
            locale=row.locale,
            title=row.title,
            body=row.body,
            default_title=default_title,
            default_body=default_body,
            allowed_placeholders=sorted(ALLOWED_PLACEHOLDERS[advisory_type]),
        )


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]


class TemplateInput(BaseModel):
    # Length limits live in one place: ``templates.validate_template``
    # (MAX_TITLE_LENGTH / MAX_BODY_LENGTH), which answers with the coded
    # ``site_template.invalid`` error instead of a bare 422.
    title: StrictStr
    body: StrictStr
    model_config = ConfigDict(extra="forbid")


class TemplateItemInput(TemplateInput):
    advisory_type: StrictStr


class UpdateTemplatesRequest(BaseModel):
    """Bulk save: all-or-nothing; unlisted types are unchanged."""

    templates: list[TemplateItemInput] = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class UpdateTemplatesResponse(BaseModel):
    message: str
    message_code: str
    items: list[TemplateResponse]


class UpdateTemplateResponse(BaseModel):
    message: str
    message_code: str
    template: TemplateResponse
