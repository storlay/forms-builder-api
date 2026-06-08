async def test_indexes_created(app) -> None:
    db = app.state.db

    users_idx = await db.users.index_information()
    assert any(ix.get("unique") and ix["key"] == [("email", 1)] for ix in users_idx.values())

    forms_idx = await db.forms.index_information()
    assert any(ix["key"] == [("owner_id", 1), ("status", 1)] for ix in forms_idx.values())

    fv_idx = await db.form_versions.index_information()
    assert any(
        ix.get("unique") and ix["key"] == [("form_id", 1), ("version", 1)] for ix in fv_idx.values()
    )

    draft_idx = await db.draft_responses.index_information()
    assert any(ix.get("expireAfterSeconds") == 0 for ix in draft_idx.values())
