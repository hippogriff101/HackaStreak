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

## Do it yourself

Go to api.slack.com/apps/ and make a new one

give it perms, creat commands etc.

you need a `SLACK_BOT_TOKEN` and a `SLACK_APP_TOKEN`!
_don't commit your.env_

this is not detailed, i will fix later!