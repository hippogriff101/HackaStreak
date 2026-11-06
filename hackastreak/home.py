from . import db

HELP_TEXT = (
    "*How to use HackaStreak* :fire:\n"
    "• `/hackastreak <username>` – see anyone's current <https://hackatime.hackclub.com|Hackatime> streak\n"
    "• `/hackastreak set <username>` – link your Hackatime username to your Slack account\n"
    "• `/hackastreak` – once linked, shows your own streak\n\n"
    "Your Hackatime username is the one in your profile URL, e.g. `hackatime.hackclub.com/@freddie`. "
    "Private profiles can't be looked up."
)


def when(ts):
    return f"<!date^{ts}^{{date_short_pretty}} {{time}}|{ts}>"


def section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:3000]}}


def lines(rows, fmt, empty="_nothing yet_"):
    return "\n".join(fmt(r) for r in rows) or empty


def help_view():
    return {"type": "home", "blocks": [section(HELP_TEXT)]}


def admin_view():
    s = db.stats()
    peak = max((d["n"] for d in s["daily"]), default=1)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "HackaStreak usage"}},
        {
            "type": "actions",
            "elements": [{"type": "button", "action_id": "home_refresh", "text": {"type": "plain_text", "text": "Refresh"}}],
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Today (UTC)*\n{s['today']} uses, {s['unique_today']} people"},
                {"type": "mrkdwn", "text": f"*Last 7 days*\n{s['week']} uses"},
                {"type": "mrkdwn", "text": f"*All time*\n{s['total']} uses, {s['unique_users']} people"},
                {"type": "mrkdwn", "text": f"*Linked accounts*\n{s['linked_users']}"},
                {"type": "mrkdwn", "text": f"*Errors*\n{s['errors']}"},
                {"type": "mrkdwn", "text": "*By type*\n" + lines(s["by_kind"], lambda r: f"{r['kind']}: {r['n']}", "–")},
            ],
        },
        {"type": "divider"},
        section("*Daily usage*\n" + lines(
            s["daily"],
            lambda r: f"`{r['day']}` {'█' * max(1, round(r['n'] / peak * 20))} {r['n']} ({r['users']} people)",
        )),
        section("*Top users*\n" + lines(
            s["top_users"],
            lambda r: f"<@{r['slack_id']}> – {r['n']} uses, last {when(r['last'])}",
        )),
        section("*Most looked-up usernames*\n" + lines(s["top_lookups"], lambda r: f"`{r['detail']}` – {r['n']}")),
        {"type": "divider"},
        section("*Latest activity*\n" + lines(
            s["recent"],
            lambda r: f"{when(r['ts'])} <@{r['slack_id']}> *{r['kind']}*"
            + (f" `{r['detail']}`" if r["detail"] else "")
            + (f" → {r['outcome']}" if r["outcome"] else "")
            # DMs don't render as channel links
            + (f" in <#{r['channel_id']}>" if r["channel_id"] and r["channel_id"][0] in "CG" else ""),
        )),
        section("*Linked accounts*\n" + lines(
            s["users"],
            lambda r: f"<@{r['slack_id']}> → `{r['username']}` (set {when(r['updated_at'])})",
        )),
        {"type": "divider"},
        section(HELP_TEXT),
    ]
    return {"type": "home", "blocks": blocks}
