
## 🧠 Medtrain – Running and Deployment Guide

### 🚀 Running the App Locally

To run **Medtrain** locally:

1. Open your terminal and navigate to the project’s root directory.  

2. Execute the shell script to start the local environment:
   ```bash
   ./run_local.sh

This script launches the local web interface and starts the Medtrain application.
	3.	Make sure the .env file is set correctly. Among the environment variables:
	•	PIPELINE_PASSWORD – set the password to access the creation form.
	•	FLASK_SECRET_KEY – random password that helps hash the user’s session key — do not touch or expose.
	•	OPENAI_API_KEY – API access key taken from OpenAI.

⸻

☁️ Deploying to Google Cloud

To deploy the application to Google Cloud Run:
	1.	Make sure you’re authenticated with gcloud and the correct project is set:

gcloud auth login
gcloud config set project medtrain


	2.	Deploy the app using the following command:

gcloud run deploy app --source .

	•	app is the name of the service being deployed.
	•	--source . tells Google Cloud to build and deploy from the current directory.

	3.	Once deployed, ensure that all environment variables and secrets are updated in your Google Cloud instance.
Update both Environment Variables and Secrets under the Cloud Run configuration.
3.1. Create a secret in Secret Manager for the secrets (not all the env vars, as it’s more expensive).
Type “secret manager” in console.cloud.google.com and add them as secrets.
3.2. Go to Cloud Run → Services → “app” → Revisions → Edit and deploy new revision → Bind the secret and add the vars under Secrets and Variables.
3.3. Done - click Deploy.


	

