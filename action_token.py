import json
import re
def get_action_token(session):
    url = "https://gemini.google.com/app"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    }
    session.headers.update(headers)
    response = session.get(url,verify=False)
    print(f"Status Code: {response.status_code}")
    html_response = response.text  # Your HTML string here
    # Extract the JSON block assigned to window.WIZ_global_data
    match = re.search(r'window\.WIZ_global_data\s*=\s*(\{.*?\});', html_response)

    if match:
        data_json = match.group(1)
        data = json.loads(data_json)

        # Access the specific key
        snl_value = data.get("SNlM0e")
        return {"at":snl_value}
    else:
        print("WIZ_global_data object not found.")
        return {"at":None}