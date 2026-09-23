"""Telegram-бот для O.S.A.

Запускается через `osa serve --transport=telegram`. Polling режим.

Команды бота:
    /start    - приветствие и список команд
    /help     - помощь
    /status   - статус агента и последние цели
    <текст>   - поставить цель агенту (вызывает run_goal)

Whitelist через OSA_TELEGRAM__ALLOWED_USERS — только указанные user_id
могут общаться с ботом. Это базовая безопасность.

Long-running goals: после получения цели бот сразу отвечает "Принял,
работаю..." и обновляет сообщение с финальным результатом. Это решает
проблему 30-секундного timeout Telegram для HTTP request.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from osa.config import OSAConfig
from osa.logging_setup import get_logger


logger = logging.getLogger("osa.telegram")


HELP_TEXT = """🐝 *O.S.A.* — Операционная Система Агента

*Команды:*
/start — приветствие
/help — эта справка
/status — статус агента и последние цели
/cancel — отменить текущую цель (если поддерживается)

*Любое сообщение* = новая цель для агента.

Примеры:
• Прочитай note.txt и перескажи
• Создай Python-проект hello с тестами
• Покажи какие файлы в sandbox

⚠️ Команды shell запрашивают подтверждение в чате (Y/N)."""


class TelegramBot:
    """Обёртка над python-telegram-bot для O.S.A."""

    def __init__(self, config: OSAConfig) -> None:
        self.config = config
        if not config.telegram.bot_token:
            raise ValueError(
                "Telegram bot_token не задан. "
                "Установите OSA_TELEGRAM__BOT_TOKEN или llm.bot_token в config.toml."
            )
        self.token = config.telegram.bot_token
        self.allowed_users = set(config.telegram.allowed_users)
        self.log = get_logger("osa.telegram")

    def _is_allowed(self, user_id: int) -> bool:
        """Проверить whitelist. Если allowed_users пуст — разрешить всем (dev-режим)."""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещён")
            return

        await update.message.reply_text(
            f"👋 Привет, {update.effective_user.first_name}!\n\n"
            f"Я — O.S.A., автономный агент на базе Minimax.\n"
            f"Напиши мне любую задачу — я попробую её решить.\n\n"
            f"/help — список команд"
        )

    async def _cmd_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            return
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            return

        from osa.db import connect

        conn = connect()
        recent_goals = conn.execute(
            "SELECT id, description, status, created_at FROM goals "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()

        if not recent_goals:
            await update.message.reply_text("📭 Целей пока нет")
            return

        lines = ["📊 *Последние 5 целей:*\n"]
        for g in recent_goals:
            status_emoji = {
                "done": "✅", "failed": "❌", "running": "⏳", "paused": "⏸"
            }.get(g["status"], "•")
            desc = g["description"][:60]
            lines.append(f"{status_emoji} `#{g['id']}` {desc}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _handle_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Любое текстовое сообщение = новая цель."""
        if not update.effective_user or not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        if not self._is_allowed(user_id):
            await update.message.reply_text("⛔ Доступ запрещён")
            return

        goal_text = update.message.text.strip()
        if not goal_text:
            return

        # Отвечаем сразу, чтобы не упереться в 30-сек timeout
        placeholder = await update.message.reply_text(
            f"⏳ Принял цель, работаю...\n\n`{goal_text[:200]}`",
            parse_mode=ParseMode.MARKDOWN,
        )

        # Показываем "печатает..."
        await update.effective_chat.send_action(ChatAction.TYPING)

        try:
            from osa.runtime.engine import run_goal
            from osa.runtime.react import ReactConfig

            react_config = ReactConfig(auto_approve=self.config.telegram.auto_approve)
            result = run_goal(goal_text, react_config)

            summary = result.plan_text_summary()
            status_line = f"\n\n*Статус:* {'✅ done' if result.status == 'done' else '❌ failed'}"
            if result.failed_task:
                status_line += f"\n*Провалена:* {result.failed_task.description[:80]}"
                status_line += f"\n*Причина:* {result.failure_reason}"

            # Telegram имеет лимит 4096 символов на сообщение
            full_response = summary + status_line
            if len(full_response) > 4000:
                full_response = full_response[:4000] + "\n\n_... (обрезано)_"

            await placeholder.edit_text(
                full_response,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            self.log.exception("telegram_goal_failed", extra={"error": str(e)})
            await placeholder.edit_text(
                f"❌ Ошибка при выполнении:\n\n`{str(e)[:3000]}`",
                parse_mode=ParseMode.MARKDOWN,
            )

    def run(self) -> None:
        """Запустить бота (blocking)."""
        self.log.info(
            "telegram_bot_starting",
            extra={"allowed_users": list(self.allowed_users) or "all"},
        )

        app = Application.builder().token(self.token).build()

        # Handlers
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

        self.log.info("telegram_bot_started")
        # run_polling блокирует
        app.run_polling(
            poll_interval=1.0,
            timeout=self.config.telegram.poll_timeout,
        )


def run_telegram_bot(config: OSAConfig) -> None:
    """Entry point для CLI."""
    bot = TelegramBot(config)
    bot.run()
