## 🧠 Medtrain – Overview and Deployment Guide

### Introduction

**Medtrain** is a web application built to enhance medical education through interactive quizzes and streamlined workflows. It enables users to securely create, access, and manage training pipelines. Specifically, the app converts a “takeaways document” into an automatically generated Google Form quiz based on its key points—helping ensure that the intended audience thoroughly reads and engages with the material. The application supports multiple authentication modes and can run locally or be deployed in Service Account (SA) mode on Google Cloud for scalable, secure access.

---

### Environment Variables

Medtrain relies on several environment variables to configure its behavior and secure its operations. These variables should be set either in your local `.env` file or in the deployment environment (e.g., Google Cloud Run):

- **PIPELINE_PASSWORD**  
  Password required to access the creation form for new training pipelines.

- **FLASK_SECRET_KEY**  
  A random secret key used by Flask to securely hash user session cookies. This should be kept secret and never exposed publicly.

- **OPENAI_API_KEY**  
  API key for accessing OpenAI services integrated within the application.

- **Other variables** may be required depending on authentication mode and deployment specifics (see below).

---

### Authentication Modes

Medtrain supports two primary authentication modes:

- **OAuth Mode**  
  Uses OAuth credentials to authenticate users via Google's OAuth service. Requires a `client_secret.json` file with OAuth client credentials.

- **Service Account Mode**  
  Uses a Google Service Account with a private key to authenticate. The service account must have access to the necessary Google Forms and resources, which may require sharing the forms with the service account's email.

---

### Running the App Locally

To run Medtrain locally, follow the instructions below based on your chosen authentication mode.

#### OAuth Mode

- Ensure you have a `client_secret.json` file containing your OAuth client credentials placed in the project root or appropriate config directory.
- Run the local environment using the provided shell script:

    ```bash
    ./run_local.sh
    ```

- This will start the local web interface and launch the Medtrain application with OAuth authentication enabled.

#### Service Account Mode

- Obtain the private key JSON file for your Google Service Account.
- Set the environment variables accordingly, including paths to the private key.
- Run the local environment with the same script:

    ```bash
    ./run_local.sh
    ```

- The application will authenticate using the service account and access the forms as configured.

---

### Deploying and Running on Google Cloud

To deploy Medtrain on Google Cloud Run, follow these steps:

1. Authenticate and set your Google Cloud project:

    ```bash
    gcloud auth login
    gcloud config set project medtrain
    ```

2. Deploy the application from the current directory:

    ```bash
    gcloud run deploy app --source .
    ```

   - `app` is the name of the Cloud Run service.
   - `--source .` directs Google Cloud to build and deploy from the current directory.

3. Configure environment variables and secrets:

   - Set environment variables such as `PIPELINE_PASSWORD`, `FLASK_SECRET_KEY`, and `OPENAI_API_KEY` in the Cloud Run service configuration.
   - For sensitive data (e.g., private keys), use **Secret Manager**:
     - Create secrets in **Secret Manager** via the Google Cloud Console.
     - Bind these secrets to your Cloud Run service under **Secrets and Variables** in the revision settings.
     - Deploy the new revision after binding.

4. Authentication Modes in the Cloud:

   - **OAuth Mode**:  
     Upload your OAuth `client_secret.json` credentials as secrets or environment variables. Users will authenticate manually via OAuth login when accessing the app.

   - **Service Account Mode**:  
     Upload the service account private key as a secret. The service account will authenticate automatically and must have appropriate access to shared Google Forms and resources.

5. After configuration, click **Deploy** to finalize the deployment.

6. TODO:
- Update the readme with how to run the app on SA and how to mount a volume
- Create deployment pipeline 
- Decide about where to store the forms
- FinOps
- Map to nicer domain