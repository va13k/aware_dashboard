import json
import logging
import os
import re
import uuid
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt

from aware_light_config_Django import settings

logger = logging.getLogger(__name__)
storage_path = settings.STORAGE_DIR


@ensure_csrf_cookie
def get_token(request):
    return HttpResponse("success")


@csrf_exempt
def save_json_file(request):
    if request.method == "POST":
        json_str = request.body
        json_dict = json.loads(json_str)
        raw_text = json_dict.get('text', None)
        try:
            content = json.loads(raw_text)
        except (TypeError, json.JSONDecodeError):
            content = raw_text

        file_name = save(content)
        return HttpResponse(
            json.dumps({
                "success": True,
                "file_name": file_name,
                "url": f"/studies/{file_name}",
            }),
            content_type="application/json",
        )

    return HttpResponse(
        json.dumps({"success": False, "message": "Invalid request method"}),
        status=405,
        content_type="application/json",
    )


def save(content):
    folder = os.path.exists(storage_path)
    if not folder:
        os.makedirs(storage_path)

    file_name = build_file_name(content)
    file_path = os.path.join(storage_path, file_name)

    with open(file_path, 'w', encoding='utf-8') as file:
        if isinstance(content, (dict, list)):
            json.dump(content, file, indent=2)
            file.write("\n")
        else:
            file.write(str(content))

    return file_name


def build_file_name(content):
    if isinstance(content, dict):
        study_id = content.get("_id")
        if study_id:
            return f"{sanitize_filename(study_id)}.json"

    return str(uuid.uuid4()) + ".json"


def sanitize_filename(value):
    return re.sub(r'[^A-Za-z0-9._-]', '-', str(value))
