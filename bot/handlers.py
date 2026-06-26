import os
from datetime import datetime
from bot.clients import bot, BOT_INFO, store
from bot.config import COMMIT_SHA, HF_SPACE_ID, HOSTING_LABEL, MODEL, RATE_LIMIT
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.preferences import get_provider, set_provider
from bot.rate_limit import is_rate_limited
from bot.clients import store
last_bot_reply = {}
from telebot.types import BotCommand

bot.set_my_commands([
    BotCommand("start", "Start"),
    BotCommand("help", "Help"),
    BotCommand("about", "About"),
    BotCommand("translate", "Translate last reply"),
    BotCommand("remember", "Remember something"),
    BotCommand("recall", "Show memories"),
    BotCommand("compliment", "Generate compliment"),
    BotCommand("կատակ", "Generate joke"),
])

# Verbose console logging for local dev and teaching. Enabled by
# BOT_VERBOSE_LOG=1 (run_local.py sets this automatically). Prints one
# line per inbound/outbound message so kids and teachers can see the
# conversation flow in their terminal while the bot is running.
VERBOSE_LOG = os.environ.get("BOT_VERBOSE_LOG", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _log(message, direction: str, text: str) -> None:
    """Print a one-line trace of a message in verbose mode.

    direction is "in" (user → bot) or "out" (bot → user). Text is
    truncated to 500 characters so long AI replies don't flood the
    terminal. Newlines are collapsed for single-line readability.
    """
    if not VERBOSE_LOG:
        return
    user = message.from_user
    user_name = (
        f"@{user.username}" if user.username else (user.first_name or f"user:{user.id}")
    )
    bot_name = f"@{BOT_INFO.username}"
    snippet = (text or "").replace("\n", " ").replace("\r", " ")
    if len(snippet) > 500:
        snippet = snippet[:500] + "..."
    if direction == "in":
        sender, receiver = user_name, bot_name
    else:
        sender, receiver = bot_name, user_name
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {sender} → {receiver}: {snippet}", flush=True)


@bot.message_handler(commands=["start"], func=is_allowed)
def cmd_start(message):
    prompt = """
    Generate a short welcome message for a student using an AI learning assistant.

    Requirements:
    - Friendly and natural tone
    - Explain that the bot teaches step by step
    - Encourage the user to ask questions
    - Mention /help briefly
    - Keep it short
    """

    response = ask_ai(message.from_user.id, prompt)

    bot.send_message(message.chat.id, response)






@bot.message_handler(commands=["reset"], func=is_allowed)
def cmd_reset(message):
    clear_history(message.from_user.id)
    bot.send_message(message.chat.id, "Conversation cleared. Starting fresh!")


@bot.message_handler(commands=["about"], func=is_allowed)
def cmd_about(message):
    if HF_SPACE_ID:
        provider = get_provider(message.from_user.id)
        model_line = f"{MODEL} (main)" if provider == "main" else f"{HF_SPACE_ID} (hf)"
    else:
        model_line = MODEL
    storage_line = "SQLite" if store is not None else "stateless (no memory)"
    lines = [
        f"Model  : {model_line}",
        f"Storage: {storage_line}",
        f"Hosting: {HOSTING_LABEL}",
    ]
    if COMMIT_SHA:
        lines.append(f"Version: {COMMIT_SHA}")
    bot.send_message(message.chat.id, "\n".join(lines))


if HF_SPACE_ID:

    @bot.message_handler(commands=["model"], func=is_allowed)
    def cmd_model(message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 1:
            current = get_provider(message.from_user.id)
            bot.send_message(
                message.chat.id,
                f"Current provider: {current}\n\n"
                "Options:\n"
                "/model main — Cerebras (fast, multilingual, with memory)\n"
                "/model hf — ArmGPT (Armenian only, slow, no memory)",
            )
            return
        choice = parts[1].strip().lower()
        if choice not in ("main", "hf"):
            bot.send_message(
                message.chat.id, "Invalid choice. Use: /model main or /model hf"
            )
            return
        if not set_provider(message.from_user.id, choice):
            bot.send_message(
                message.chat.id, "Could not save preference. Try again later."
            )
            return
        if choice == "hf":
            bot.send_message(
                message.chat.id,
                "Switched to hf (ArmGPT).\n\n"
                "Note: this is a tiny base completion model trained only on Armenian text. "
                "It will continue whatever you write rather than answer questions, "
                "and it does not understand English. Replies take ~30-60s and there is no memory.",
            )
        else:
            bot.send_message(message.chat.id, "Switched to Main Provider.")


@bot.message_handler(content_types=["text"], func=is_allowed)
def handle_message(message):
    if not should_respond(message):
        return
    text = (message.text or "").replace(f"@{BOT_INFO.username}", "").strip()
    if not text:
        # Edited messages, forwards, or stickers-with-empty-caption can
        # arrive with no usable text. Don't burn rate-limit / AI calls on them.
        return
    _log(message, "in", text)
    if is_rate_limited(message.from_user.id):
        limit_msg = f"You've reached the daily limit of {RATE_LIMIT} messages. Try again tomorrow."
        bot.send_message(message.chat.id, limit_msg)
        _log(message, "out", f"[rate limited] {limit_msg}")
        return
    try:
        with keep_typing(message.chat.id):
           reply = ask_ai(message.from_user.id, text)
           last_bot_reply[message.from_user.id] = reply
          
        send_reply(message, reply)
        _log(message, "out", reply)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        bot.send_message(message.chat.id, "Something went wrong. Please try again.")
        _log(message, "out", f"[error] {e}")

        
        @bot.message_handler(commands=["compliment"], func=is_allowed)
        def cmd_compliment(message):
            parts = (message.text or "").split(maxsplit=1)

            # Optional name after command
            target = parts[1].strip() if len(parts) > 1 else "friend"

            prompt = f"""
            Create a short positive compliment for {target}.

            Requirements:
            - Friendly and encouraging
            - Suitable for students
            - One or two sentences only
            - Reply in Armenian
            """

            try:
                compliment = ask_ai(message.from_user.id, prompt)
                bot.send_message(message.chat.id, compliment)
            except Exception:
                bot.send_message(
                    message.chat.id,
                    "Չհաջողվեց ստեղծել գովեստը։ Փորձեք նորից։"
                )
@bot.message_handler(commands=["կատակ"], func=is_allowed)
def cmd_joke(message):
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "Օգտագործում՝ /կատակ դպրոց\n/կատակ ծրագրավորում\n/կատակ BMW"
        )
        return

    topic = parts[1].strip()

    prompt = f"""
    Create a funny, family-friendly joke about: {topic}

    Requirements:
    - One short joke
    - Suitable for students
    - Funny but not offensive
    - Reply in Armenian
    """

    try:
        joke = ask_ai(message.from_user.id, prompt)
        bot.send_message(message.chat.id, joke)
    except Exception:
        bot.send_message(
            message.chat.id,
            "Չհաջողվեց ստեղծել կատակ։ Փորձեք նորից։"
        )

def remember(user_id: int, text: str):
    if store is None:
        return False

    cur = store.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            memory TEXT
        )
    """)

    cur.execute(
        "INSERT INTO memories (user_id, memory) VALUES (?, ?)",
        (user_id, text),
    )

    store.commit()
    return True


def recall(user_id: int):
    if store is None:
        return []

    cur = store.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            memory TEXT
        )
    """)

    cur.execute(
        "SELECT memory FROM memories WHERE user_id=?",
        (user_id,),
    )

    return [row[0] for row in cur.fetchall()]
@bot.message_handler(commands=["remember"], func=is_allowed)
def cmd_remember(message):
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "Օգտագործում՝ /remember իմ անունը Արմեն է"
        )
        return

    text = parts[1].strip()

    if remember(message.from_user.id, text):
        bot.send_message(message.chat.id, "✅ Հիշեցի։")
    else:
        bot.send_message(message.chat.id, "❌ Չհաջողվեց պահպանել։")
@bot.message_handler(commands=["recall"], func=is_allowed)
def cmd_recall(message):
    memories = recall(message.from_user.id)

    if not memories:
        bot.send_message(
            message.chat.id,
            "Ես դեռ ոչինչ չեմ հիշում։"
        )
        return

    text = "\n".join(
        f"{i+1}. {m}"
        for i, m in enumerate(memories)
    )

    bot.send_message(
        message.chat.id,
        f"📚 Հիշում եմ՝\n\n{text}"
    )

import re

@bot.message_handler(commands=["translate"], func=is_allowed)
def cmd_translate(message):

    reply = last_bot_reply.get(message.from_user.id)

    if not reply:
        bot.send_message(
            message.chat.id,
            "Թարգմանելու համար նախ ստացեք բոտից պատասխան։"
        )
        return

    # Detect Armenian
    if re.search(r"[Ա-Ֆա-ֆ]", reply):
        target = "English"
    else:
        target = "Armenian"

    prompt = f"""
    Translate the following text into {target}.

    Requirements:
    - Preserve meaning.
    - Do not explain.
    - Return only the translation.

    Text:
    {reply}
    """

    try:
        translated = ask_ai(message.from_user.id, prompt)

        # Save translated version as latest reply too
        last_bot_reply[message.from_user.id] = translated

        bot.send_message(message.chat.id, translated)

    except Exception:
        bot.send_message(
            message.chat.id,
            "Չհաջողվեց թարգմանել։"
        )
@bot.message_handler(commands=["help"], func=is_allowed)
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        """
Հասանելի հրամաններ

/start
/help
/about
/reset
/model
/կատակ
/compliment
/remember
/recall
/translate
"""
    )