import os
import json
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# For a description of each inference parameter, see
# https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-claude.html
KWARGS = {
    "temperature": float(os.getenv("BEDROCK_TEMPERATURE", "0.5")),
    "top_p": float(os.getenv("BEDROCK_TOP_P", "1")),
    "top_k": int(os.getenv("BEDROCK_TOP_K", "250")),
    "max_tokens": int(os.getenv("BEDROCK_MAX_TOKENS", "500")),
}

MODEL, REGION = "anthropic.claude-3-5-sonnet-20240620-v1:0", "us-east-1"

# Initialize the Bedrock LLM
llm = ChatBedrock(model_id=MODEL, model_kwargs=KWARGS, region_name=REGION)

# Define the prompt template
messages = [
    (
        "system",
        """Given the email message, produce a list of action items. Return only the JSON in the following format:

{{"ActionItemList": 
[{{"action": "Action item text"}}, 
{{"action": "Action item text"}}
]
}}""",
    ),
    ("human", "{email_content}"),
]
prompt_template = ChatPromptTemplate.from_messages(messages)


def process_email(email_content):
    """
    Process an email message and extract action items using the Bedrock Claude 3.5 model.

    :param email_content: The full text content of the email
    :return: A list of action items in JSON format
    """
    chain = prompt_template | llm | StrOutputParser()

    # Send the prompt to the model
    response = chain.invoke({"email_content": email_content})

    # Parse the JSON response
    try:
        action_items = json.loads(response)
        return action_items
    except json.JSONDecodeError:
        print(f"Error parsing JSON response: {response}")
        return {"ActionItemList": []}


def process_messages(messages, service):
    """
    Process a list of email messages and add action items to those without the 'cooked' label.
    Also adds the 'cooked' label to the message in Gmail.

    :param messages: A list of email message dictionaries
    :param service: The Gmail API service object
    :return: The updated list of email message dictionaries with action items
    """
    for message in messages:
        if "cooked" not in message.get("labels", []):
            action_items = process_email(message["full_text"])
            message["action_items"] = action_items["ActionItemList"]
            message["labels"].append("cooked")

            # Add the 'cooked' label to the message in Gmail
            try:
                # First, check if the 'cooked' label exists, if not create it
                labels = (
                    service.users()
                    .labels()
                    .list(userId="me")
                    .execute()
                    .get("labels", [])
                )
                cooked_label = next(
                    (label for label in labels if label["name"] == "cooked"), None
                )
                if not cooked_label:
                    cooked_label = (
                        service.users()
                        .labels()
                        .create(userId="me", body={"name": "cooked"})
                        .execute()
                    )

                # Now add the 'cooked' label to the message
                service.users().messages().modify(
                    userId="me",
                    id=message["id"],
                    body={"addLabelIds": [cooked_label["id"]]},
                ).execute()
            except Exception as e:
                print(
                    f"Error adding 'cooked' label to message {message['id']}: {str(e)}"
                )

    return messages
