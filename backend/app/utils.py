import io
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import botocore
import emails  # type: ignore
import requests
from jinja2 import Template
from PIL import Image

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    html_content = Template(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    message = emails.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logger.info(f"send email result: {response}")


def generate_test_email(email_to: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
    )
    return EmailData(html_content=html_content, subject=subject)


def upload_image_bytes(prefix: str, image_bytes: bytes) -> str:
    """
    Uploads image bytes to R2

    Args:
        prefix (str): The prefix to use for the key
        image_bytes (bytes): The image bytes to upload

    Returns:
        str: The URL of the uploaded image
    """
    try:
        # Initialize the S3 client
        s3 = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{settings.CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
        # set image_url
        image_url = ""
        # set key
        key = f"{prefix}{str(uuid.uuid4())}"
        # upload image
        try:
            image_data = io.BytesIO(image_bytes)  # convert image to bytes
            s3.upload_fileobj(image_data, settings.R2_BUCKET_NAME, key)  # upload image
            # image_url = (
            #     f"https://{settings.R2_BUCKET_NAME}.kevingil.com/{key}"  # set image_url
            # )
            # development url
            image_url = f"https://pub-623d4eba2d7f457ea2529bf8e09d6268.r2.dev/{key}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to upload image to R2. Error: {e}")

        return image_url
    except botocore.exceptions.ClientError as e:
        logger.error(f"Error uploading to R2: {str(e)}")
        return f"Error uploading to R2: {str(e)}"


def create_thumbnail(image_bytes: bytes, max_kb: int = 500) -> bytes:
    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")

    image.thumbnail((512, 512))  # Adjust size as needed

    for quality in range(95, 10, -5):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        size_kb = buffer.tell() / 1024
        if size_kb <= max_kb:
            buffer.seek(0)
            return buffer.read()

    raise ValueError("Could not generate thumbnail under 500KB")
