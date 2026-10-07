import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]


def get_service():
    token_file = Path("/tmp/google_token.json")

    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_file),
            SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        client_config = json.loads(
            os.environ["GOOGLE_OAUTH_CLIENT_JSON"]
        )

        flow = InstalledAppFlow.from_client_config(
            client_config,
            SCOPES
        )

        creds = flow.run_local_server(
            port=8080,
            access_type="offline",
            prompt="consent"
        )

        token_file.write_text(
            creds.to_json(),
            encoding="utf-8"
        )

    return build(
        "drive",
        "v3",
        credentials=creds,
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
