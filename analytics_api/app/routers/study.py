"""Study-wide endpoints: facts about the configuration, not about one phone."""

from fastapi import APIRouter

from app.schemas import StudyRequirementsSchema
from app.services import sensor_requirements

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/requirements", response_model=StudyRequirementsSchema)
async def get_study_requirements():
    """The sensor streams each platform's config asks phones to record."""
    return sensor_requirements.study_requirements()
