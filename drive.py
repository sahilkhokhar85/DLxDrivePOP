import base64
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]


def get_service():

    encoded = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_B64"]

    raw = base64.b64decode(encoded).decode("utf-8")
    info = json.loads(raw)

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES
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
            fields="id,name,webViewLink",
            supportsAllDrives=True
        )
        .execute()
    )

    file_id = created["id"]

    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader"
        },
        supportsAllDrives=True
    ).execute()

    return {
        "id": file_id,
        "name": created["name"],
        "url": f"https://drive.google.com/file/d/{file_id}/view"
    }
