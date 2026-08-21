"""Study-wide endpoints: facts about the configuration, not about one phone."""

from fastapi import APIRouter

from app.schemas import StudyRequirementsSchema
from app.services import sensor_requirements, study_config

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/requirements", response_model=StudyRequirementsSchema)
async def get_study_requirements():
    """The sensor streams each platform's config asks phones to record."""
    return sensor_requirements.study_requirements()


@router.get("/dataflow")
async def get_study_dataflow():
    """Where the study's data goes, and how that was established.

    Read from the deployed config rather than from the study model, because this
    is the answer the phones were actually given. iOS is reported separately and
    is always the micro-server: an iPhone has no direct-database client, so its
    path is a property of the platform rather than a choice this study made.

    `source` says whether the config declares the dataflow or whether it was read
    back out of the webservice setting. Every config generated before the field
    existed reads as inferred, which is most of them until a study is regenerated.
    """
    deployed = study_config.load_deployed_config()
    summary = deployed.summary if deployed else {}
    return {
        "android": {
            "dataflow": summary.get("dataflow"),
            "source": summary.get("dataflow_source"),
        },
        # Not read from a config: the micro-server is the iOS path by
        # construction, and no iOS config expresses a choice about it.
        "ios": {"dataflow": study_config.WEBSERVICE, "source": "platform"},
        "config_available": deployed is not None,
    }
