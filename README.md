# HackaStreak

A parcially vibe-coded Slack Bot that tells you a users's current [hackatime](hackatime.hackclub.com) streak!

[Hackatime](hackatime.hackclub.com) is a hackclub site that logs your time coding! Check out my stats at my [Hackatime public Page](hackatime.hackclub.com/@freddie)

This project is partically vibecoded as I'm new to requests and stuff but is a fun projects. Made using GPT-5, Github Copilot and my fingers on a keyboard.

> [!NOTE]
> This is currently being hosted on a Pi Zero 2 W! 

## How it works?

`/hackastreak [hackatime username]`
Calls Hackatime [API](https://hackatime.hackclub.com/api-docs/) to find if users: 
a) actually exists 
or 
b) if their stats are private
The bot also detects errors with  api or network issues.

There is also command line text to show what the app is doing:

  terminal output: `Hackatime API error: {r.status_code}` or `Fetching Hackatime stats for user: {username}`
  
  (_this could be optimised with `logger`_)


## How to run it yourself!?

Head over to api.slack.com/apps and make a new application, enable socket mode and grab the `APP TOKEN`!

Then, in slack website, make the command needed: `/hackastreak`!

Next add the following Bot Scopes:
```
commands
chat:write

```
Your good, install the app to your workspace, get the BOT TOKEN!

Now add them into your `.env`!

```
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=

```

Make sure all the dependencies are installed:
```
requests
slack-bolt
dotenv
```
Run the script!
