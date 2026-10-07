import base64
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]


def get_service():
    # OAuth client configuration
    client_config_raw = base64.b64decode(
        os.environ["GOOGLE_OAUTH_CLIENT_JSON_B64"]
    ).decode("utf-8")

    client_config = json.loads(client_config_raw)

    installed = client_config["installed"]

    # OAuth token generated from your personal Google account
    token_raw = base64.b64decode(
        os.environ["GOOGLE_OAUTH_TOKEN_B64"]
    ).decode("utf-8")

    token_data = json.loads(token_raw)

    credentials = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=installed["token_uri"],
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=SCOPES
    )

    # Automatically refresh expired access token
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials.valid:
        raise RuntimeError(
            "Google OAuth credentials are invalid or expired."
        )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False
    )


def upload_file(path):
    service = get_service()

    metadata = {
        "name": path.name,
        "parents": [FOLDER_ID]
    }

    media = MediaFileUpload(
        str(path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=16 * 1024 * 1024
    )

    created = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink"
        )
        .execute()
    )

    file_id = created["id"]

    # Make the uploaded file accessible through the Drive link
    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader"
        }
    ).execute()

    return {
        "id": file_id,
        "name": created["name"],
        "url": f"https://drive.google.com/file/d/{file_id}/view"
    }
