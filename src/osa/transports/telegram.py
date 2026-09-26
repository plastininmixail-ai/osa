"""Telegram-бот для O.S.A.

Запускается через `osa serve --transport=telegram`. Polling режим.

Команды бота:
    /start   - приветствие и список команд
    /help    - помощь
    /status  - статус агента и последние цели
    <текст>  - поставить цель агенту (вызывает run_goal)

Безопасность:
- Whitelist через OSA_TELEGRAM__ALLOWED_USERS
- Risk-based execution:
  * SAFE (ls, cat, pwd, echo, head, tail, grep, find, du, df)
    — выполняются без подтверждения
  * MEDIUM (mv, cp, redirect >, curl/wget без изменений)
    — пропускаются, в логе помечаются как medium_risk
  * HIGH/CRITICAL (rm, chmod, sudo, apt install, format)
    — выполняются, но в лог пишется CRITICAL и пользователь получает
    предупреждение в финальном ответе

Для Telegram-бота: используется auto_approve=True на уровне engine,
потому что engine.run() синхронный и не может ждать асинхронного
ответа от пользователя. Реальный inline-кнопочный confirm будет в M2
после рефакторинга engine на async.
"""

from __future__ import annotations

import logging

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

*Любое сообщение* = новая цель для агента.

Примеры:
• Прочитай note.txt и перескажи
• Создай Python-проект hello с тестами
• Покажи какие файлы в sandbox

⚠️ Shell-команды: безопасные (ls, cat, pwd) выполняются без подтверждения.
Опасные (rm, sudo) выполняются с пометкой в логе — см. `osa logs`.
"""


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
        # Логгер переписки: каждое сообщение user+agent дописывается в chat_log.txt
        from osa.runtime.chat_logger import ChatLogger
        self.chat_logger = ChatLogger()

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

        await update.effective_chat.send_action(ChatAction.TYPING)

        # Heartbeat: обновляем placeholder каждые 15 сек, чтобы пользователь видел
        # что бот не завис. Сложные задачи (особенно с многошаговой декомпозицией)
        # могут идти 2-5 минут — без heartbeat это выглядит как зависание.
        import asyncio

        start_ts = asyncio.get_event_loop().time()
        stop_heartbeat = asyncio.Event()

        async def heartbeat():
            while not stop_heartbeat.is_set():
                await asyncio.sleep(15)
                if stop_heartbeat.is_set():
                    break
                try:
                    elapsed = int(asyncio.get_event_loop().time() - start_ts)
                    await placeholder.edit_text(
                        f"⏳ Работаю... {elapsed}s\n\n`{goal_text[:200]}`",
                    )
                    await update.effective_chat.send_action(ChatAction.TYPING)
                except Exception:
                    # Если edit_text не сработал — просто пропускаем
                    pass

        heartbeat_task = asyncio.create_task(heartbeat())

        try:
            from osa.runtime.engine import run_goal
            from osa.runtime.react import ReactConfig

            # Для Telegram-бота: auto_approve=True чтобы engine.run()
            # не зависал на синхронном typer.prompt().
            # Risk-based классификация в ReactLoop пропускает SAFE команды
            # автоматически, а MEDIUM+ всё равно выполняются, но помечаются
            # в логе через shell_safe_command или отдельный warning.
            # Реальный inline-кнопочный confirm будет в M2 после рефакторинга
            # engine на async.
            react_config = ReactConfig(auto_approve=True)
            result = run_goal(goal_text, react_config)

            full_response = self._format_response(result)

            # Умная обрезка если превышает Telegram лимит (4096)
            full_response, was_truncated = self._smart_truncate(full_response, max_len=4000)

            if was_truncated:
                self.log.info(
                    "telegram_response_truncated",
                    extra={"original_len": len(self._format_response(result))},
                )

            # Telegram Markdown парсер ломается на неэкранированных _ * [
            # если они не образуют пары. Безопаснее отправлять plain text —
            # теряется только жирный шрифт в шапке.
            try:
                await placeholder.edit_text(
                    full_response,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as edit_err:
                self.log.warning(
                    "telegram_markdown_failed",
                    extra={"error": str(edit_err)[:200]},
                )
                # Fallback: отправляем как plain text
                await placeholder.edit_text(full_response)

            # Логируем переписку в chat_log.txt
            try:
                self.chat_logger.log_exchange(
                    goal_text,
                    full_response,
                    goal_id=result.goal_id,
                    status=result.status,
                )
            except Exception as log_err:
                self.log.warning(
                    "chat_log_write_failed",
                    extra={"error": str(log_err)[:200]},
                )

            # Останавливаем heartbeat
            stop_heartbeat.set()
            try:
                await asyncio.wait_for(heartbeat_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                heartbeat_task.cancel()

        except Exception as e:
            self.log.exception("telegram_goal_failed", extra={"error": str(e)})
            # Останавливаем heartbeat и в случае ошибки
            stop_heartbeat.set()
            try:
                await asyncio.wait_for(heartbeat_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                heartbeat_task.cancel()

            try:
                await placeholder.edit_text(
                    f"❌ Ошибка при выполнении:\n\n{str(e)[:3000]}",
                )
            except Exception:
                await placeholder.reply_text(
                    f"❌ Ошибка при выполнении:\n\n{str(e)[:3000]}",
                )

            # Логируем даже при ошибке
            try:
                self.chat_logger.log_user(goal_text, user_id=user_id)
                self.chat_logger.log_agent(f"ERROR: {str(e)[:1000]}", user_id=user_id)
            except Exception:
                pass

    @staticmethod
    def _format_response(result) -> str:
        """Форматирует ответ для Telegram.

        Длинные ответы обрезаются по границе секции (\\n\\n) с предупреждением.
        Полный текст всегда доступен через `osa logs` или экспорт цели.
        """
        # Финальный текст ответа из последней done-task
        final_answer = ""
        if result.plan.tasks:
            for task in reversed(result.plan.tasks):
                if task.status == "done" and task.result:
                    final_answer = task.result
                    break
            if not final_answer and result.plan.tasks[-1].result:
                final_answer = result.plan.tasks[-1].result

        status_line = (
            f"\n\n——\n📊 *Статус:* {'✅ done' if result.status == 'done' else '❌ failed'}"
            f" · {len(result.plan.tasks)} шагов"
        )
        if result.failed_task:
            status_line += f"\n*Провалена:* {result.failed_task.description[:80]}"
            status_line += f"\n*Причина:* {result.failure_reason}"

        if not final_answer:
            return result.plan_text_summary() + status_line

        return final_answer + status_line

    @staticmethod
    def _smart_truncate(text: str, max_len: int = 4000) -> tuple[str, bool]:
        """Умная обрезка текста по границе секции.

        Returns:
            (truncated_text, was_truncated)
        """
        if len(text) <= max_len:
            return text, False

        # Резервируем место для пометки об обрезке
        marker = f"\n\n_... (обрезано, показано {max_len}/{len(text)} символов. Полный текст в `osa logs` или БД)_"
        budget = max_len - len(marker)

        if budget < 100:
            return text[:max_len] + marker, True

        truncated = text[:budget]

        # Пытаемся обрезать по последней границе секции (\n\n) в пределах budget
        last_section_break = truncated.rfind("\n\n")
        if last_section_break > budget * 0.7:  # Если нашли разумную границу
            truncated = truncated[:last_section_break]

        # Если всё ещё не влезает — режем по последнему пробелу
        elif " " in truncated:
            last_space = truncated.rfind(" ")
            if last_space > budget * 0.8:
                truncated = truncated[:last_space]

        return truncated + marker, True

    def run(self) -> None:
        """Запустить бота (blocking)."""
        self.log.info(
            "telegram_bot_starting",
            extra={"allowed_users": list(self.allowed_users) or "all"},
        )

        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

        self.log.info("telegram_bot_started")
        app.run_polling(
            poll_interval=1.0,
            timeout=self.config.telegram.poll_timeout,
        )


def run_telegram_bot(config: OSAConfig) -> None:
    """Entry point для CLI."""
    bot = TelegramBot(config)
    bot.run()
