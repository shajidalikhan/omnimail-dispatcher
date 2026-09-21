# Deploying OmniMail Dispatcher to Render (Step-by-Step Guide)

Follow this step-by-step guide to deploy your **OmniMail Dispatcher** application to [Render.com](https://render.com) for free with automated HTTPS and password protection.

---

## Pre-requisites
1. A free account on [GitHub.com](https://github.com).
2. A free account on [Render.com](https://render.com).
3. Git installed on your computer.

---

## Step 1: Initialize Git and Push to GitHub

1. Open your terminal or Command Prompt in the `email dispatcher` folder:
   ```bash
   cd "d:\Study Material\Computer Science and Application\M.Tech\Semester 3\TA Work\email dispatcher"
   ```

2. Initialize a Git repository (your `.gitignore` file already prevents passwords and `.env` from being uploaded):
   ```bash
   git init
   git add .
   git commit -m "Initial commit for OmniMail Dispatcher"
   ```

3. Create a **Private Repository** on [GitHub](https://github.com/new) named `omnimail-dispatcher`.

4. Link and push your code to GitHub:
   ```bash
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/omnimail-dispatcher.git
   git branch -M main
   git push -u origin main
   ```

---

## Step 2: Create a Web Service on Render

1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click the **+ New** button in the top navigation bar and select **Web Service**.
3. Under **Connect a repository**, find and select your `omnimail-dispatcher` repository (click *Connect*).
4. Configure the service with the following settings:
   - **Name**: `omnimail-dispatcher` (or any custom name)
   - **Region**: Select the region closest to you (e.g., *Singapore*, *Frankfurt*, or *Oregon*)
   - **Branch**: `main`
   - **Root Directory**: *(leave blank)*
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn backend.app:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: Select **Free**

---

## Step 3: Configure Security & Environment Variables

Scroll down to the **Environment Variables** section on the Render setup page and add:

| Key | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `AUTH_ENABLED` | `true` | Enables login protection for your live website |
| `ADMIN_USERNAME` | `admin` *(or your custom username)* | Username required to access the dashboard |
| `ADMIN_PASSWORD` | *(create a strong password)* | Password required to unlock the site |
| `DEFAULT_DISPATCHER` | `gmail` | Default dispatcher choice |
| `SENDER_EMAIL` | *(Optional - your sending email)* | Pre-fills your sender email |
| `SENDER_NAME` | *(Optional - your name/title)* | Pre-fills your display name |
| `SENDER_KEY` | *(Optional - 16-char App Password)* | Pre-fills your mail key (or enter in UI) |

> [!TIP]
> You don't have to enter your App Password in Render's environment variables if you prefer to type it directly into the UI when you want to send emails.

---

## Step 4: Deploy and Access

1. Click **Deploy Web Service** at the bottom of the page.
2. Render will automatically download the dependencies, compile the app, and start the server.
3. In 2–3 minutes, the status will show **Live** with a green dot.
4. Click your live URL (e.g., `https://omnimail-dispatcher.onrender.com`).
5. A native browser authentication popup will appear:
   - Enter your `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
6. You are in! You can now import spreadsheets, craft personalized templates, and launch email dispatching from any phone, laptop, or tablet.
