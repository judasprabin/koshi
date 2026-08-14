from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koshi.db import get_session
from koshi.insights import generate_ceiling_insight
from koshi.models.ceiling_usage import CeilingUsage
from koshi.models.eoi_rounds import EoiRound
from koshi.models.occupation_momentum import OccupationMomentum
from koshi.models.occupations import Occupation
from koshi.schemas.occupation import OccupationProfile, SourcedFact

router = APIRouter(prefix="/v1/occupations", tags=["occupations"])


@router.get("/{code}", response_model=OccupationProfile)
def get_occupation(code: str, session: Session = Depends(get_session)) -> OccupationProfile:
    occupation = session.get(Occupation, code)
    if occupation is None:
        raise HTTPException(status_code=404, detail=f"unknown occupation code {code!r}")

    latest_ceiling = session.scalar(
        select(CeilingUsage).where(CeilingUsage.occupation_code == code).order_by(CeilingUsage.as_of_date.desc())
    )
    if latest_ceiling is None:
        raise HTTPException(status_code=404, detail=f"no ceiling data for {code!r} yet")

    latest_round = session.scalar(
        select(EoiRound).where(EoiRound.occupation_code == code).order_by(EoiRound.round_date.desc())
    )
    latest_momentum = session.scalar(
        select(OccupationMomentum)
        .where(OccupationMomentum.occupation_code == code)
        .order_by(OccupationMomentum.computed_at.desc())
    )

    insight = generate_ceiling_insight(
        issued=latest_ceiling.issued,
        ceiling=latest_ceiling.ceiling,
        direction=latest_momentum.direction if latest_momentum else "steady",
    )

    return OccupationProfile(
        code=occupation.code,
        name=occupation.name,
        unit_group=occupation.unit_group,
        ceiling_issued=SourcedFact(
            value=latest_ceiling.issued,
            reliability_tier=latest_ceiling.reliability_tier,
            retrieved_at=latest_ceiling.retrieved_at,
            source_url=latest_ceiling.source_url,
        ),
        ceiling_cap=SourcedFact(
            value=latest_ceiling.ceiling,
            reliability_tier=latest_ceiling.reliability_tier,
            retrieved_at=latest_ceiling.retrieved_at,
            source_url=latest_ceiling.source_url,
        ),
        places_left=latest_ceiling.ceiling - latest_ceiling.issued,
        latest_threshold=(
            SourcedFact(
                value=latest_round.threshold_points,
                reliability_tier=latest_round.reliability_tier,
                retrieved_at=latest_round.retrieved_at,
                source_url=latest_round.source_url,
            )
            if latest_round
            else None
        ),
        momentum=latest_momentum.direction if latest_momentum else None,
        insight=insight,
    )
