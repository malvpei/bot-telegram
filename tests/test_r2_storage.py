from dataclasses import replace

import pytest

from app.config import get_settings
from app.r2_storage import R2StorageClient, R2StorageError


def test_r2_access_key_id_must_have_expected_length():
    settings = replace(
        get_settings(),
        r2_account_id="acct",
        r2_access_key_id="too-short",
        r2_secret_access_key="secret",
        r2_bucket="videos",
    )
    client = R2StorageClient(settings)

    with pytest.raises(R2StorageError, match="32 caracteres"):
        client._boto_client()
