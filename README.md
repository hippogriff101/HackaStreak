# HackaStreak

A partially vibe-coded Slack bot that tells you a user's current [Hackatime](https://hackatime.hackclub.com) streak!

[Hackatime](https://hackatime.hackclub.com) is a Hack Club site that logs your time coding! Check out my stats on my [Hackatime public page](https://hackatime.hackclub.com/@freddie).

This project is partially vibe-coded as I'm new to requests and stuff, but it's a fun project. Made using GPT-5, GitHub Copilot, Claude and my fingers on a keyboard.

> [!NOTE]
> This is currently hosted on a Pi Zero 2 W!

## Usage

| Command | What it does |
| --- | --- |
| `/hackastreak <username>` | Shows anyone's current streak |
| `/hackastreak set <username>` | Links your Hackatime username to your Slack account |
| `/hackastreak` | Shows your own streak (once linked) |

@mention the bot, or say "hackastreak" in the pingword channel, and it'll react with :eyes_shaking: and send you a message only you can see explaining how to use it.

Admins (set in `.env`) get usage stats on the bot's App Home tab: who's using it, how often, recent activity and linked accounts.

All data comes from the [Hackatime API](https://hackatime.hackclub.com/api-docs/). Linked accounts and usage logs are kept in a local SQLite file.

## Running it yourself

1. Go to [api.slack.com/apps](https://api.slack.com/apps), **Create New App → From a manifest** and paste in [manifest.yml](manifest.yml).
2. Under **Basic Information**, create an app-level token with the `connections:write` scope. That's your `SLACK_APP_TOKEN`.
3. Install the app to your workspace and copy the **Bot User OAuth Token**. That's your `SLACK_BOT_TOKEN`.
4. Copy `.env.example` to `.env` and fill it in.
5. Invite the bot to the pingword channel (`/invite @HackaStreak`).

It uses Socket Mode, so nothing needs to be exposed to the internet. It just needs outbound access to Slack and Hackatime.

### Raspberry Pi

```sh
git clone <this repo> ~/hackastreak && cd ~/hackastreak
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill it in
.venv/bin/python -m hackastreak
```

To keep it running in the background, use the systemd unit in [deploy/](deploy/hackastreak.service) (change `User` and the paths if needed):

```sh
sudo cp deploy/hackastreak.service /etc/systemd/system/
sudo systemctl enable --now hackastreak
journalctl -u hackastreak -f
```

### Docker / Orchard

```sh
docker build -t hackastreak .
docker run -d --restart unless-stopped --env-file .env -v hackastreak-data:/data hackastreak
```

The database lives in `/data`, so mount a volume there to keep it between restarts. No ports need to be opened.
