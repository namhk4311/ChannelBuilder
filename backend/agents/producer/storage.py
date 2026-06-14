"""MinIO client + bucket bootstrap. Dùng bên trong package video."""
from __future__ import annotations

import json
import logging

from minio import Minio

from config import (
    BUCKET_MUSIC,
    BUCKET_OUTPUTS,
    BUCKET_SOURCES,
    MINIO_ACCESS,
    MINIO_ENDPOINT,
    MINIO_SECRET,
    MINIO_SECURE,
)

log = logging.getLogger(__name__)

# Single client instance, dùng chung trong package
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=MINIO_SECURE,
)


def init_buckets() -> None:
    """
    Tạo 3 bucket idempotent. `outputs` + `music` được set public-read để link
    xem/download chạy trực tiếp trong browser không cần auth.
    """
    log.info("init_buckets: connect %s (secure=%s)", MINIO_ENDPOINT, MINIO_SECURE)
    for b in (BUCKET_SOURCES, BUCKET_OUTPUTS, BUCKET_MUSIC):
        if not minio_client.bucket_exists(b):
            minio_client.make_bucket(b)
            log.info("init_buckets: created bucket %s", b)
        else:
            log.debug("init_buckets: bucket %s already exists", b)

    for b in (BUCKET_OUTPUTS, BUCKET_MUSIC):
        public_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{b}/*"],
            }],
        }
        minio_client.set_bucket_policy(b, json.dumps(public_policy))
    log.info("init_buckets: ready (sources=%s, outputs=%s, music=%s public-read)",
             BUCKET_SOURCES, BUCKET_OUTPUTS, BUCKET_MUSIC)
