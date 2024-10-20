import json
import os
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import base64
from bedrock import process_messages


def lambda_handler(event, context):
    print(json.dumps(event))

    # Check if we have credentials in the cookies
    creds = get_credentials_from_cookies(event)

    # Check if this is a redirect from OAuth
    if (
        "queryStringParameters" in event
        and "code" in event["queryStringParameters"]
        and creds is None
    ):
        # Load the client configuration from the local file
        client_config = json.load(open("gcp.json"))

        # Set up the OAuth 2.0 flow
        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.labels",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
            redirect_uri=client_config["web"]["redirect_uris"][0],
        )

        # Exchange the authorization code for credentials
        flow.fetch_token(code=event["queryStringParameters"]["code"])

        # Get the credentials
        creds = flow.credentials

        # Build the Gmail API service
        service = build("gmail", "v1", credentials=creds)

        # Retrieve the last 10 messages from the inbox
        results = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=10)
            .execute()
        )
        messages = results.get("messages", [])

        if not messages:
            return create_response(
                json.dumps({"message": "No messages found in the inbox."}),
                set_cookie=create_credentials_cookie(creds),
            )
        else:
            output = generate_messages_output(service, messages)

            return create_response(
                json.dumps({"messages": output}),
                set_cookie=create_credentials_cookie(creds),
            )

    # If we don't have valid credentials, start the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Load the client configuration from the local file
            client_config = json.load(open("gcp.json"))

            # Set up the OAuth 2.0 flow
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=[
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.labels",
                    "https://www.googleapis.com/auth/gmail.modify",
                ],
                redirect_uri=client_config["web"]["redirect_uris"][0],
            )

            # Redirect the user to the authorization URL
            auth_url, _ = flow.authorization_url(prompt="consent")
            return {"statusCode": 302, "headers": {"Location": auth_url}}

    # Build the Gmail API service
    service = build("gmail", "v1", credentials=creds)

    # Retrieve the last 10 messages
    results = service.users().messages().list(userId="me", maxResults=10).execute()
    messages = results.get("messages", [])

    if not messages:
        return create_response(
            json.dumps({"message": "No messages found."}),
            set_cookie=create_credentials_cookie(creds),
        )
    else:
        output = generate_messages_output(service, messages)

        return create_response(
            json.dumps(output), set_cookie=create_credentials_cookie(creds)
        )


def get_credentials_from_cookies(event):
    if "cookies" in event:
        cookies = event["cookies"]
        for cookie in cookies:
            if cookie.startswith("credentials="):
                credentials_value = cookie.split("=", 1)[1]
                creds_json = base64.b64decode(credentials_value).decode("utf-8")
                return Credentials.from_authorized_user_info(json.loads(creds_json))
    return None


def create_credentials_cookie(creds):
    creds_json = creds.to_json()
    encoded_creds = base64.b64encode(creds_json.encode("utf-8")).decode("utf-8")
    return (
        f"credentials={encoded_creds}; HttpOnly; Secure; SameSite=Strict; Max-Age=3600"
    )


def create_response(
    body,
    status_code=200,
    headers=None,
    content_type="application/json",
    set_cookie=None,
):
    response = {
        "statusCode": status_code,
        "body": body,
        "headers": headers or {},
    }
    response["headers"]["Content-Type"] = content_type
    if set_cookie:
        response["headers"]["Set-Cookie"] = set_cookie
    return response


def get_message_text(msg):
    if "data" in msg["payload"]["body"]:
        return base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode("utf-8")
    elif "parts" in msg["payload"]:
        for part in msg["payload"]["parts"]:
            if part["mimeType"] == "text/plain":
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
    return "No text content found in the message."


def generate_messages_output(service, messages):
    output = []
    # Get all labels first
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label_dict = {label["id"]: label["name"] for label in labels}

    for message in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message["id"], format="full")
            .execute()
        )
        subject = next(
            (
                header["value"]
                for header in msg["payload"]["headers"]
                if header["name"] == "Subject"
            ),
            "No Subject",
        )
        sender = next(
            (
                header["value"]
                for header in msg["payload"]["headers"]
                if header["name"] == "From"
            ),
            "Unknown Sender",
        )
        label_names = [
            label_dict.get(label_id, label_id) for label_id in msg.get("labelIds", [])
        ]
        full_message_text = get_message_text(msg)

        output.append(
            {
                "id": msg["id"],
                "subject": subject,
                "sender": sender,
                "full_text": full_message_text,
                "labels": label_names,
            }
        )
        # Process messages to add action items
    processed_output = process_messages(output, service)
    return processed_output
