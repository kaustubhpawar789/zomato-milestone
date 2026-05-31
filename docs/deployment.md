# Deploying Zomato AI on Render

Because the Zomato AI application uses a **FastAPI** backend with a custom HTML/JS frontend (instead of Streamlit), it requires a hosting platform capable of running standard Python web servers. **Render.com** is an excellent platform for this, offering a 100% free tier that does not require a credit card.

Follow these steps to get your app live on the internet.

---

## Prerequisites

1. A [GitHub](https://github.com/) account.
2. A [Render.com](https://render.com/) account.
3. Ensure your local code is committed and pushed to a GitHub repository.

## Deployment Steps

### Step 1: Push to GitHub
If you haven't already, push your `ZOMATO-MILESTONE` folder to a new repository on GitHub. Open your terminal in the project folder and run:
```bash
git init
git add .
git commit -m "Initial commit for Zomato AI"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

### Step 2: Create a Web Service on Render
1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click the **New +** button in the top right and select **Web Service**.
3. Select **Build and deploy from a Git repository**.
4. Connect your GitHub account if you haven't already, and select the repository you created in Step 1.

### Step 3: Configure the Web Service
Render will automatically detect that this is a Python project, but verify the following settings on the configuration page:

- **Name:** Choose a name for your app (e.g., `zomato-ai-recommender`).
- **Environment:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT` (Note: Render will also automatically read the `Procfile` we created in the root directory if you leave this blank).
- **Instance Type:** Select the **Free** tier option.

Click **Create Web Service** at the bottom of the page.

### Step 4: Wait for Deployment
Render will now clone your repository, install the packages, and launch the server. You can monitor the progress in the logs section on the screen. 

This process usually takes 2-5 minutes. Once you see `Uvicorn running on http://0.0.0.0:10000` (or similar) in the logs, your app is live!

### Step 5: View Your Live App
Click the URL located at the top left of the dashboard below your app name (it will look something like `https://zomato-ai-recommender.onrender.com`). Share this link with anyone!

---

## Troubleshooting

- **Build Failure (Timeout):** The free tier on Render has limited resources. If it times out installing `pandas` or `datasets`, simply click "Manual Deploy" -> "Clear build cache & deploy" to try again.
- **App falls asleep:** Note that free instances on Render will "spin down" after 15 minutes of inactivity. When you visit the app after it has spun down, it may take 30-50 seconds to wake up for the first request.
