# Telegram Bot Notifications

The harness can post bot updates to an existing Telegram chat, group, channel,
or forum topic. Telegram bots cannot create a user channel by API; create the
chat/channel in Telegram, add the bot, then give the harness the bot token and
chat id.

## Environment

```bash
export RPA_TELEGRAM_ENABLED=1
export RPA_TELEGRAM_BOT_TOKEN="set-from-botfather"
export RPA_TELEGRAM_CHAT_ID="set-chat-or-channel-id"
```

Optional:

```bash
export RPA_TELEGRAM_THREAD_ID="123"
export RPA_TELEGRAM_STRICT=1
```

Use `RPA_TELEGRAM_THREAD_ID` for Telegram forum topics when you want Slack-like
bot lanes inside one group.

For named topic routing, set topic ids:

```bash
export RPA_TELEGRAM_TOPIC_REPORTS="9"
export RPA_TELEGRAM_TOPIC_QUESTIONS="10"
export RPA_TELEGRAM_TOPIC_FAILURES="11"
export RPA_TELEGRAM_TOPIC_RANTS="12"
export RPA_TELEGRAM_TOPIC_DEPLOYMENTS="13"
export RPA_TELEGRAM_TOPIC_MEMORIES="14"
```

## Commands

```bash
python main.py --telegram-message "RPA bot online"
python main.py --telegram-message "Memory indexed" --telegram-topic memories
python main.py --telegram-question "Should I retry the failed invoice workflow?"
python main.py --telegram-rant "Login page changed twice today" --telegram-rant "Selector cache is stale"
python main.py --telegram-discover-chat
```

After the environment variables are set, normal test and workflow runs post a
short report automatically:

```bash
python main.py --discover ./tests --run --report html,json
```

## Setup Notes

1. Create the bot with BotFather and keep the token out of source control.
2. Create a Telegram group/channel such as `RPA Bot Reports`.
3. Add the bot as a member. For channels, grant permission to post.
4. Send one message in the chat, then run `python main.py --telegram-discover-chat`
   to find chat ids visible to the bot.
5. Put the selected id in `RPA_TELEGRAM_CHAT_ID`.
