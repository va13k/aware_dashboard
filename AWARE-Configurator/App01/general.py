import json
import logging
import os
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt

from aware_light_config_Django import settings

logger = logging.getLogger(__name__)
storage_path = settings.STORAGE_DIR
STUDY_CONFIG_FILE_NAME = "studyConfig.json"


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
                "url": f"/studies/files/{file_name}",
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

    file_path = os.path.join(storage_path, STUDY_CONFIG_FILE_NAME)

    with open(file_path, 'w', encoding='utf-8') as file:
        if isinstance(content, (dict, list)):
            json.dump(content, file, indent=2)
            file.write("\n")
        else:
            file.write(str(content))

    return STUDY_CONFIG_FILE_NAME
