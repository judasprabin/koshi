from fastapi.testclient import TestClient

from koshi.main import app


def test_openapi_schema_lists_this_slices_paths():
    client = TestClient(app)
    response = client.get("/v1/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/v1/occupations/{code}" in schema["paths"]
    assert "/v1/occupations" in schema["paths"]
    assert "/v1/healthz" in schema["paths"]


def _referenced_schema_names(property_schema: dict) -> set[str]:
    """Collect every `#/components/schemas/X` ref name reachable from a
    property schema, whether the property is a direct $ref (SourcedFact) or
    a `Foo | None` anyOf (SourcedFact | None)."""
    names = set()
    if "$ref" in property_schema:
        names.add(property_schema["$ref"].rsplit("/", 1)[-1])
    for sub_schema in property_schema.get("anyOf", []):
        names |= _referenced_schema_names(sub_schema)
    return names


def test_occupation_profile_sourced_and_derived_facts_carry_provenance():
    """Provenance-on-every-fact is the single most load-bearing constraint
    in this slice (design spec §3) — a client must be able to tell a
    scraped/curated fact (SourcedFact: reliability_tier, retrieved_at,
    source_url) from a computed one (DerivedFact: reliability_tier,
    computed_at) apart from `/v1/occupations/{code}`'s path merely
    existing."""
    client = TestClient(app)
    schema = client.get("/v1/openapi.json").json()
    components = schema["components"]["schemas"]
    profile = components["OccupationProfile"]

    referenced = set()
    for property_schema in profile["properties"].values():
        referenced |= _referenced_schema_names(property_schema)

    assert "SourcedFact" in referenced, (
        "OccupationProfile no longer references a SourcedFact sub-schema — "
        "expected ceiling_issued/ceiling_cap/latest_threshold to carry provenance"
    )
    assert "DerivedFact" in referenced, (
        "OccupationProfile no longer references a DerivedFact sub-schema — "
        "expected momentum to carry provenance"
    )

    sourced_fact_props = components["SourcedFact"]["properties"]
    assert "reliability_tier" in sourced_fact_props
    assert "retrieved_at" in sourced_fact_props

    derived_fact_props = components["DerivedFact"]["properties"]
    assert "reliability_tier" in derived_fact_props
    assert "computed_at" in derived_fact_props
