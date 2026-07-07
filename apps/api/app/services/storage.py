from functools import lru_cache

import boto3

from app.core.config import settings


@lru_cache
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )


def put_object(key: str, data: bytes, content_type: str = "image/tiff") -> None:
    get_s3_client().put_object(
        Bucket=settings.s3_bucket_analysis, Key=key, Body=data, ContentType=content_type
    )


def object_exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        get_s3_client().head_object(Bucket=settings.s3_bucket_analysis, Key=key)
        return True
    except ClientError:
        return False
