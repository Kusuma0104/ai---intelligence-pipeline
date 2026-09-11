from dotenv import load_dotenv
import os
import requests

load_dotenv()

token = os.getenv("GITHUB_TOKEN")

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
}

url = "https://api.github.com/repos/openai/openai-python"

response = requests.get(url, headers=headers)

print("GitHub API status:", response.status_code)

data = response.json()

print("Repository:", data.get("full_name"))
print("Stars:", data.get("stargazers_count"))