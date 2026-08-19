from flask import Flask, request, jsonify
import requests, json, re, urllib3, os
import uuid
from action_token import get_action_token
from available_models import get_models

app = Flask(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
url = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
params = {
    "bl": "boq_assistant-bard-web-server_20260716.08_p0",
    "f.sid": "-6520936063234361995",
    "hl": "en-GB",
    "_reqid": "4049185",
    "rt": "c"
}


def build_model_config(model_hash: str) -> list:
    client_uuid = str(uuid.uuid4()).upper()
    return f'[1,null,null,null,"{model_hash}",null,null,null,[4,5,6,8],null,null,null,null,null,1,1,"{client_uuid}"]'


PLACEHOLDER_RE = re.compile(r'^http://googleusercontent\.com/image_generation_content/\d+\s*$')


def send_message(session, action_token, message, language, conversation_id, response_id, choice_id):
    inner_array = [
        [message, 0, None, None, None, None, 0],
        [language],
        [conversation_id, response_id, choice_id, None, None, None, None, None, None, ""],
        "",
        "", None, [1], 1, None, None, 1, 0,
        None, None, None, None, None, [[0]], 0,
        None, None, None, None, None, None, None, None, 1,
        None, None, [4], None, None, None, None, None, None, None, None, None, None,
        [1], None, None, None, None, None, None, None, None, None, None, None,
        0, None, None, None, None, None,
        str(uuid.uuid4()),
        None, [1], None, None, None, None, None, None,
        2, None, None, None, None, None, None, None, None, None, None,
        1, 1, None, None, None, None, None, None, None, None, None, None, 0
    ]
    payload = {
        "f.req": json.dumps([None, json.dumps(inner_array)]),
        "at": action_token.get("at")
    }
    # Sending the POST request
    response = session.post(url, params=params, stream=True, data=payload, verify=False)
    full_text = ""
    printed_len = 0
    seen_images = set()

    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue
        full_text += line + "\n"

        parsed = parse_response(full_text)

        text_state = parsed.get("text")
        if text_state and len(text_state) > printed_len:
            new_chunk = text_state[printed_len:]
            printed_len = len(text_state)
            # skip the internal image placeholder token, it's not real content
            if not PLACEHOLDER_RE.match(text_state.strip()):
                print(new_chunk, end="", flush=True)
        for img_url in parsed.get("image_urls", []):
            if img_url not in seen_images:
                seen_images.add(img_url)
                print(f"\n[image] {img_url}")

    print()
    return full_text


IMAGE_URL_RE = re.compile(r'^https://lh3\.googleusercontent\.com/gg-dl/')


def _find_image_urls(node, urls):
    if isinstance(node, str):
        if IMAGE_URL_RE.match(node):
            urls.append(node)
    elif isinstance(node, list):
        for item in node:
            _find_image_urls(item, urls)
    elif isinstance(node, dict):
        for v in node.values():
            _find_image_urls(v, urls)


def parse_response(raw_text):
    blocks = re.split(r'\n\d+\n', raw_text)
    result = {}
    image_urls = []

    for block in blocks:
        block = block.strip()
        if not block or not block.startswith('[["wrb.fr"'):
            continue
        try:
            outer = json.loads(block)
        except json.JSONDecodeError:
            continue

        for entry in outer:
            if not isinstance(entry, list) or len(entry) < 3 or entry[0] != "wrb.fr":
                continue
            inner_raw = entry[2]
            if not inner_raw:
                continue
            try:
                inner = json.loads(inner_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if len(inner) > 1 and isinstance(inner[1], list) and len(inner[1]) >= 2:
                result["conversation_id"] = inner[1][0]
                result["response_id"] = inner[1][1]

            if len(inner) > 4 and isinstance(inner[4], list) and inner[4]:
                candidate = inner[4][0]
                if isinstance(candidate, list) and len(candidate) > 1:
                    result["choice_id"] = candidate[0]
                    text_field = candidate[1]
                    if isinstance(text_field, list) and text_field and isinstance(text_field[0], str):
                        result["text"] = text_field[0]

            # scan the WHOLE inner block, not just candidate — position of
            # the image tuple shifts between responses
            _find_image_urls(inner, image_urls)

    if image_urls:
        result["image_urls"] = list(dict.fromkeys(image_urls))

    return result


def set_cookies():
    with open("cookies.json", "r") as f:
        cookies = json.load(f)
    return cookies


def get_header(selected_model):
    headers = {
        "x-goog-ext-525001261-jspb": build_model_config(selected_model),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    }
    return headers


# --- File saving functions for persistent chat ---
CONV_FILE = "conversation_state.json"


def load_conv_state():
    if os.path.exists(CONV_FILE):
        with open(CONV_FILE, "r") as f:
            return json.load(f)
    return {"conversation_id": "", "response_id": "", "choice_id": ""}


def save_conv_state(conv_id, resp_id, cho_id):
    with open(CONV_FILE, "w") as f:
        json.dump({
            "conversation_id": conv_id or "",
            "response_id": resp_id or "",
            "choice_id": cho_id or ""
        }, f, indent=4)


# --- Flask API Routes ---

@app.route('/set_cookies', methods=['POST'])
def api_set_cookies():
    data = request.json
    psid = data.get("__Secure-1PSID")
    psidts = data.get("__Secure-1PSIDTS")

    if not psid or not psidts:
        return jsonify({"success": False, "error": "Both __Secure-1PSID and __Secure-1PSIDTS are required"}), 400

    cookie_data = {
        "__Secure-1PSID": psid,
        "__Secure-1PSIDTS": psidts
    }

    # Save to cookies.json
    with open("cookies.json", "w") as f:
        json.dump(cookie_data, f, indent=4)

    # Test connection and fetch available models
    try:
        session = requests.session()
        session.cookies.update(cookie_data)
        action_token = get_action_token(session=session)
        models = get_models(session=session, action_token=action_token)

        return jsonify({
            "success": True,
            "message": "Cookies saved successfully.",
            "available_models": models
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/set_model', methods=['POST'])
def api_set_model():
    data = request.json
    model_hash = data.get("model_hash")

    if not model_hash:
        return jsonify({"success": False, "error": "model_hash is required"}), 400

    model_data = {
        "model": model_hash
    }

    with open("model.json", "w") as f:
        json.dump(model_data, f, indent=4)

    return jsonify({"success": True, "message": "Model saved successfully to model.json"})


@app.route('/chat', methods=['POST'])
def chat():
    # Read input from the POST request body
    data = request.json
    msg = data.get("message")

    # Check if we should continue previous chat (supports boolean True or string "true")
    prev_chat_cont = data.get("previous_chat_continue", "false")
    should_continue = str(prev_chat_cont).lower() == "true"

    if not msg:
        return jsonify({"success": False, "error": "Message is required"}), 400

    session = requests.session()

    try:
        cookies = set_cookies()
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Cookies not found. Please use /set_cookies first."}), 400

    try:
        with open("model.json", "r") as f:
            model_id = json.load(f)
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Model not found. Please use /set_model first."}), 400

    selected_model = model_id.get("model")
    headers = get_header(selected_model)
    session.cookies.update(cookies)

    try:
        action_token = get_action_token(session=session)
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Failed to get action token. Ensure cookies are valid. Error: {str(e)}"}), 500

    session.headers.update(headers)
    language = "en-GB"

    # Logic to continue or start fresh
    if should_continue:
        state = load_conv_state()
        conversation_id = state.get("conversation_id", "")
        response_id = state.get("response_id", "")
        choice_id = state.get("choice_id", "")
    else:
        conversation_id = ""
        response_id = ""
        choice_id = ""
        # Wipe the file so an old state isn't accidentally loaded later
        save_conv_state("", "", "")

    # Send message exactly as before
    result = send_message(session, action_token, msg, language, conversation_id, response_id, choice_id)

    # Parse the text and new IDs
    get_details = parse_response(result)

    # Update IDs
    conversation_id = get_details.get("conversation_id", conversation_id)
    response_id = get_details.get("response_id", response_id)
    choice_id = get_details.get("choice_id", choice_id)

    # Save the updated IDs to the file so it remembers context for the next request
    save_conv_state(conversation_id, response_id, choice_id)

    session.close()

    # Return as JSON API response
    return jsonify({
        "success": True,
        "text": get_details.get("text", ""),
        "image_urls": get_details.get("image_urls", []),
        "conversation_id": conversation_id
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)