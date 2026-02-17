import os
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))
    
@app.command("/hackastreak")
def streak_command(ack, respond, command):
    ack()
    print("I got a command!")
    username = command.get("text", "").strip()

    if not username:
        print("No username provided.")
        respond("Hey there, thats not how ya use *hackastreak*, try this instead: `/hackastreak <hackatime_username>`")
        return

    try:
        print(f"Fetching Hackatime stats for user: {username}")
        r = requests.get(
            f"https://hackatime.hackclub.com/api/v1/users/{username}/stats",
            headers={"accept": "application/json"}
        )

        if r.status_code == 404:
            print("They putt in a username that doesn't exist.")
            respond(f"User '{username}' does not exist.")
            return

        if r.status_code == 403:
            print("They putt in a username that has a private profile.")
            respond(f"User '{username}' has a private profile.")
            return

        if r.status_code != 200:
            print(f"Hackatime API error: {r.status_code}")
            respond(f"Hackatime API error ({r.status_code}). Try again later.")
            return

        data = r.json()
        streak = int(data["data"].get("streak", 0))

        respond(f"🔥 {username}'s current Hackatime streak is {streak} day/s.")
        print(f"Successfully fetched streak for {username}: {streak} day/s.")

    except requests.exceptions.RequestException:
        print("Network error while connecting to Hackatime API.")
        respond("Could not connect to Hackatime API.")
    except Exception:
        print("An unexpected error occurred.")
        respond("Unexpected error occurred.")

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()
