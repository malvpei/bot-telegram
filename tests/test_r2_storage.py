from dataclasses import replace
from io import BytesIO

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


class FakePaginator:
    def paginate(self, **kwargs):
        return [
            {
                "Contents": [
                    {"Key": "imagenes/a.jpg", "Size": 10},
                    {"Key": "imagenes/b.png", "Size": 20},
                    {"Key": "imagenes/snap:image/jpeg", "Size": 25},
                    {"Key": "imagenes/not-image", "Size": 26},
                    {"Key": "imagenes/video.mp4", "Size": 30},
                    {"Key": "imagenes/folder/", "Size": 0},
                ]
            }
        ]


class FakeBotoClient:
    def __init__(self):
        self.put_calls = []
        self.objects = {"imagenes/a.jpg": (b"image", "image/jpeg")}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator()

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs):
        body, content_type = self.objects[kwargs["Key"]]
        return {"Body": BytesIO(body), "ContentType": content_type}

    def head_object(self, **kwargs):
        content_type_by_key = {
            "imagenes/snap:image/jpeg": "image/jpeg",
            "imagenes/not-image": "text/plain",
        }
        return {"ContentType": content_type_by_key[kwargs["Key"]]}


def test_r2_lists_and_uploads_images():
    settings = replace(
        get_settings(),
        r2_account_id="acct",
        r2_access_key_id="x" * 32,
        r2_secret_access_key="secret",
        r2_bucket="bucket",
    )
    client = R2StorageClient(settings)
    fake = FakeBotoClient()
    client._client = fake

    images = client.list_images("imagenes")
    uploaded = client.upload_bytes(
        "imagenes/new.png",
        b"png",
        content_type="image/png",
    )
    data, content_type = client.download_bytes("imagenes/a.jpg")

    assert [image.key for image in images] == [
        "imagenes/a.jpg",
        "imagenes/b.png",
        "imagenes/snap:image/jpeg",
    ]
    assert uploaded.key == "imagenes/new.png"
    assert fake.put_calls[0]["Bucket"] == "bucket"
    assert fake.put_calls[0]["ContentType"] == "image/png"
    assert data == b"image"
    assert content_type == "image/jpeg"
