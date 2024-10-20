## Setting up Gmail API Credentials for AWS Lambda

To use the Gmail API in your AWS Lambda function to access your personal Gmail inbox, you'll need to set up OAuth 2.0 credentials. Here's the recommended approach:

1. **Create a Google Cloud Project:**

   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a new project or select an existing one.
   - Enable the Gmail API for your project.

2. **Create OAuth 2.0 Credentials:**

   - In the Google Cloud Console, go to "APIs & Services" > "Credentials".
   - Click "Create Credentials" and select "OAuth client ID".
   - Choose "Desktop app" as the application type.
   - Download the client configuration file (JSON).

3. **Store Credentials Securely:**

   - **DO NOT** include the client configuration directly in your Lambda function code or repository.
   - Use AWS Secrets Manager:
     - Go to the AWS Secrets Manager console.
     - Create a new secret.
     - Store the entire contents of the client configuration JSON as the secret value.
     - Note the ARN of the secret for later use.

4. **Obtain Refresh Token:**

   - You'll need to run a one-time authorization flow on your local machine to get a refresh token.
   - Use a script like this to get the refresh token:

     ```python
     from google_auth_oauthlib.flow import Flow
     from google.auth.transport.requests import Request

     flow = Flow.from_client_secrets_file(
         'path/to/client_configuration.json',
         scopes=['https://www.googleapis.com/auth/gmail.readonly']
     )

     flow.run_local_server(port=8080, prompt='consent')

     credentials = flow.credentials
     print(f"Refresh Token: {credentials.refresh_token}")
     ```

   - Store this refresh token in AWS Secrets Manager along with the client configuration.

5. **Grant Lambda Access to Secrets Manager:**

   - In your Lambda function's execution role, add permissions to access Secrets Manager.
   - Add the `secretsmanager:GetSecretValue` permission for the specific secret ARN.

6. **Use Credentials in Lambda:**

   - In your Lambda function, retrieve the secret and use it to authenticate:

     ```python
     import boto3
     import json
     from google.oauth2.credentials import Credentials
     from googleapiclient.discovery import build

     def get_gmail_credentials():
         secret_name = "your-secret-name"
         region_name = "your-aws-region"

         session = boto3.session.Session()
         client = session.client(service_name='secretsmanager', region_name=region_name)

         try:
             get_secret_value_response = client.get_secret_value(SecretId=secret_name)
             secret = json.loads(get_secret_value_response['SecretString'])

             return Credentials(
                 None,  # No access token needed as we'll use refresh token
                 refresh_token=secret['refresh_token'],
                 token_uri="https://oauth2.googleapis.com/token",
                 client_id=secret['client_id'],
                 client_secret=secret['client_secret']
             )
         except Exception as e:
             raise e

     def lambda_handler(event, context):
         credentials = get_gmail_credentials()
         gmail_service = build('gmail', 'v1', credentials=credentials)

         # Now you can use gmail_service to access your Gmail inbox
         # For example:
         # messages = gmail_service.users().messages().list(userId='me').execute()

         return {
             'statusCode': 200,
             'body': json.dumps('Successfully accessed Gmail')
         }
     ```

This approach allows your AWS Lambda function to access your personal Gmail inbox using OAuth 2.0 authentication. Remember to handle token refresh and error cases in your production code.

Note: Ensure you comply with Google's terms of service and your organization's policies when accessing personal Gmail data from a server-side application.
