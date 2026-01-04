## 🧠 Medtrain – Overview and Deployment Guide

### Introduction

**MedTrain** is an educational application designed to help users generate quizzes and Google Forms from uploaded documents, improving comprehension and engagement with learning materials.

The product is available in two interfaces:
- **Web Application** – users upload a document via a secure web interface and receive an automatically generated quiz.
- **WhatsApp Bot** – users initiate a conversation on WhatsApp and voluntarily send a document to receive a generated quiz or form.

MedTrain operates **only on user-initiated requests**. Users must actively contact the service and submit a document. The system does **not** send marketing messages, bulk messages, or unsolicited communications, and does not initiate conversations with users.

The application can run locally or be deployed on Google Cloud using a Google Service Account for secure, scalable access to Google Forms.

**Contact:** alonlesman@gmail.com

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
- Create deployment pipeline 
- Decide about where to store the forms
- FinOps
- Map to nicer domain