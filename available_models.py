import uuid
import json
import re
def get_models(session,action_token):
    url = "https://gemini.google.com/_/BardChatUi/data/batchexecute"

    headers = {
        "x-goog-ext-525001261-jspb": f'[1,null,null,null,null,null,null,null,[4,5,6,8],null,null,null,null,null,null,null,"{str(uuid.uuid4())}"]',
        
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    }
    # Query parameters
    params = {
        "rpcids": "otAQ7b",
        "source-path": "/",
        "bl": "boq_assistant-bard-web-server_20260716.08_p0",
        "f.sid": "4955096486147164424",
        "hl": "en",
        "_reqid": "36256",
        "rt": "c"
    }

    # Form data payload
    data = {
        "f.req": '[[["otAQ7b","[]",null,"generic"]]]',
        "at": action_token.get("at")
    }
    session.headers.update(headers)
    # Send the POST request
    response = session.post(url, params=params, data=data,verify=False)
    MODEL_IDS = parse_all_model_ids(response.text)
    return MODEL_IDS

def parse_all_model_ids(raw_response: str) -> dict:
    model_ids = {}

    # 1. Safely extract the wrb.fr payload
    match = re.search(r'\["wrb\.fr",\s*"[^"]*",\s*("(?:[^"\\]|\\.)*")', raw_response)
    if not match:
        raise ValueError("Could not find wrb.fr JSON payload in response.")

    # 2. Parse nested JSON layers safely
    inner_json_str = json.loads(match.group(1))
    data = json.loads(inner_json_str)

    # 3. Recursive function to find the models anywhere in the array
    # 3. Recursive function to find the models anywhere in the array
    def find_models(item):
        if isinstance(item, list):
            # A model definition usually looks like:
            # ["fbb127bbb056c959", "Flash", "All-around help", ...]
            if (len(item) >= 3 and
                    isinstance(item[0], str) and re.fullmatch(r'[a-f0-9]{16}', item[0]) and
                    isinstance(item[1], str) and isinstance(item[2], str)):

                name = item[1]
                # Ensure the name is short, NOT another hex hash, and not a UI label
                if (len(name) < 20 and
                        not re.fullmatch(r'[a-f0-9]{16}', name) and
                        name not in ["Files", "Sources", "Video gallery", "Aspect ratio"]):
                    model_ids[name] = item[0]

            # Keep digging deeper into nested lists
            for sub_item in item:
                find_models(sub_item)

    # Start the recursive search
    find_models(data)

    # 4. Extract "Thinking" fallback (since it is a sub-mode, not a primary model)
    if "Thinking" in raw_response and "Thinking" not in model_ids:
        if "5bf011840784117a" in raw_response:
            model_ids["Thinking"] = "5bf011840784117a"

    return model_ids
