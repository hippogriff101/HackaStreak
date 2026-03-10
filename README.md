# HackaStreak

A Slack Bot that tells you a users's current [hackatime](hackatime.hackclub.com) streak!

[Hackatime](hackatime.hackclub.com) is a hackclub site that logs your time coding! As of **now** I have [69 hours](hackatime.hackclub.com/freddie) coding on hackatime *.

This project is partically vibecoded as I'm new to requests and stuff but is a fun projects. Made using GPT-5, Github Copiolt and my fingers on a keyboard.

## How it works?

Uses python, obvs /silly
Slack Bolt, socketmode thingy.
https://hackatime.hackclub.com/api-docs/

### In testing???

`/hackastreak [hackatime username]`
calls api to find if users: exists or if they are private

errors for hackatime api, network etc.

There is also command line text to show what the app is doing

## How to run it yourself!?

Head over to api.slack.com/apps and make a new application, enable socket mode and grab the APP TOKEN!

Then, in slack website, make the command needed: `/hackastreak'!

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