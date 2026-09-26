"""ReAct loop — основной цикл рассуждения агента.

Цикл:
  1. LLM получает system prompt + history + доступные tools
  2. LLM возвращает либо content (финальный ответ), либо tool_calls
  3. Если tool_calls — выполняем их, добавляем результаты в history, идём к 1
  4. Повторяем пока не получим content или не упрёмся в max_iterations

Системный промпт хранится в коде на M1a. В M1c — версионируется в БД.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, ToolSpec
from osa.llm.tool_calls import ToolCallRequest, ToolCallResult
from osa.logging_setup import get_logger
from osa.tools.base import Tool, ToolConfirmationRequired, ToolResult
from osa.tools import registry as tool_registry


SYSTEM_PROMPT = """Ты — Урс, автономный агент операционной системы OSA.

Твоя задача: решить поставленную цель пользователя.

Правила:
1. Анализируй задачу. Если нужны дополнительные данные — вызывай инструменты.
2. Инструменты возвращают наблюдения. На основе наблюдений продолжай.
3. Когда задача решена — дай финальный ответ (НЕ вызывай инструменты).
4. Если инструмент вернул ошибку — попробуй другой подход.
5. Если задача нерешаема с доступными инструментами — скажи честно.
6. Отвечай на русском. Кратко и по делу.

{available_skills}
"""


@dataclass
class ReactConfig:
    """Конфигурация ReAct loop.

    max_iterations: жёсткий лимит итераций (защита от зацикливания)
    max_total_tokens: лимит суммарных токенов на задачу (защита от трат)
    max_tokens: лимит токенов на один LLM-вызов
    """

    max_iterations: int = 15
    max_total_tokens: int = 50000  # 50K токенов на задачу — достаточно для сложных
    max_tokens: int = 2000  # лимит на один вызов
    temperature: float = 0.7
    auto_approve: bool = False  # True для CI/headless


@dataclass
class ReactStep:
    """Один шаг loop'а для логирования."""

    iteration: int
    thought: str  # контент от LLM (если есть)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_results: list[ToolCallResult] = field(default_factory=list)
    final: bool = False


@dataclass
class ReactResult:
    """Итог ReAct loop'а."""

    final_content: str
    steps: list[ReactStep]
    total_tokens: int = 0
    iterations: int = 0


def _load_available_skills() -> str:
    """Загрузить список skills из БД и отформатировать для system prompt."""
    from osa.runtime.skills import SkillLibrary

    try:
        skills = SkillLibrary.list_all(limit=20)
    except Exception:  # noqa: BLE001
        return ""

    if not skills:
        return ""

    lines = ["\nДоступные навыки (skills) — записанные паттерны успешных действий:"]
    for skill in skills[:10]:  # лимит чтобы не раздувать промпт
        lines.append(skill.to_prompt_text())
    return "\n".join(lines)


def _system_prompt() -> str:
    return SYSTEM_PROMPT.format(available_skills=_load_available_skills())


class ReactLoop:
    """Цикл think-act-observe с native tool calling."""

    def __init__(
        self,
        provider: LLMProvider,
        tools: list[Tool] | None = None,
        config: ReactConfig | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or ReactConfig()
        self.tools = tools or tool_registry.all_tools()
        self.log = get_logger("osa.react")

    def run(self, goal_text: str) -> ReactResult:
        """Прогнать цикл до финального ответа или max_iterations."""
        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=_system_prompt()),
            LLMMessage(role="user", content=goal_text),
        ]
        tool_specs = [self._tool_to_spec(t) for t in self.tools]
        steps: list[ReactStep] = []
        total_tokens = 0
        # Tracking для отладки: какие tools использовались и сколько раз
        # Помогает при stuck detection в Reflection (M1c).
        last_tool_signature: str | None = None
        same_tool_streak = 0

        for iteration in range(1, self.config.max_iterations + 1):
            self.log.info(
                "react_iteration",
                extra={"iteration": iteration, "messages": len(messages)},
            )

            response = self.provider.complete(
                messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                tools=tool_specs,
            )
            total_tokens += response.tokens_used

            # Лимит токенов: проверяем ПОСЛЕ каждого вызова, даже перед tool_calls.
            # Это защищает от runaway — модель может бесконечно думать без action,
            # и каждый thinking тратит токены без прогресса.
            if total_tokens >= self.config.max_total_tokens:
                self.log.warning(
                    "react_token_limit",
                    extra={
                        "iteration": iteration,
                        "total_tokens": total_tokens,
                        "limit": self.config.max_total_tokens,
                    },
                )
                return ReactResult(
                    final_content=(
                        f"[Reached token limit {total_tokens}/{self.config.max_total_tokens}. "
                        f"Задача слишком сложная для текущей модели. "
                        f"Попробуй разбить на подзадачи или использовать более мощную модель.]"
                    ),
                    steps=steps,
                    total_tokens=total_tokens,
                    iterations=iteration,
                )

            # Если нет tool_calls — финальный ответ
            if not response.tool_calls:
                step = ReactStep(
                    iteration=iteration,
                    thought=response.content,
                    final=True,
                )
                steps.append(step)
                self.log.info(
                    "react_final",
                    extra={"iteration": iteration, "tokens": total_tokens},
                )
                return ReactResult(
                    final_content=response.content,
                    steps=steps,
                    total_tokens=total_tokens,
                    iterations=iteration,
                )

            # Tool calls — добавляем assistant message и выполняем
            assistant_msg = LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            step = ReactStep(
                iteration=iteration,
                thought=response.content,
                tool_calls=list(response.tool_calls),
            )

            # Выполняем инструменты
            for tc in response.tool_calls:
                tool_result = self._execute_tool(tc)
                tcr = ToolCallResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=self._serialize_tool_result(tool_result),
                )
                step.tool_results.append(tcr)
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=tcr.content,
                        tool_call_id=tc.id,
                    )
                )

            steps.append(step)

        # Достигли max_iterations
        self.log.warning(
            "react_max_iterations",
            extra={"max": self.config.max_iterations},
        )
        return ReactResult(
            final_content="[Reached max iterations without final answer]",
            steps=steps,
            total_tokens=total_tokens,
            iterations=self.config.max_iterations,
        )

    def _execute_tool(self, tc: ToolCallRequest) -> ToolResult:
        """Найти инструмент по имени, проверить подтверждение, выполнить."""
        try:
            tool = tool_registry.get(tc.name)
        except KeyError as e:
            return ToolResult(success=False, output="", error=str(e))

        # Определяем нужен ли confirm для этой команды
        needs_confirm = tool.requires_confirmation

        # Для shell: проверяем risk-level конкретной команды
        if tool.name == "shell":
            from osa.runtime.risk import assess_command

            cmd = tc.arguments.get("command", "")
            assessment = assess_command(cmd)
            if not assessment.requires_confirmation:
                needs_confirm = False  # SAFE/LOW — пропускаем подтверждение
                self.log.debug(
                    "shell_safe_command",
                    extra={
                        "command": cmd[:100],
                        "level": assessment.level_name,
                        "reasons": assessment.reasons[:3],
                    },
                )

        # Human-in-the-loop
        if needs_confirm and not self.config.auto_approve:
            if not self._confirm(tool, tc):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"User declined tool: {tc.name}",
                )

        try:
            return tool.run(**tc.arguments)
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                success=False, output="", error=f"Tool exception: {e}"
            )

    def _confirm(self, tool: Tool, tc: ToolCallRequest) -> bool:
        """Запросить подтверждение у пользователя (для shell и подобных)."""
        import typer

        # Для shell показываем risk level
        if tool.name == "shell":
            from osa.runtime.risk import assess_command

            cmd = tc.arguments.get("command", "")
            assessment = assess_command(cmd)
            typer.echo(
                f"\n⚠️  Shell command [{assessment.level_name}]: {tool.name}"
            )
            typer.echo(f"   {cmd}")
            if assessment.reasons:
                typer.echo(f"   Risk: {', '.join(assessment.reasons[:3])}")
        else:
            typer.echo(f"\n⚠️  Tool requires confirmation: {tool.name}")
            typer.echo(f"   Args: {json.dumps(tc.arguments, ensure_ascii=False)}")
        try:
            answer = typer.prompt("   Proceed? [y/N]", default="n")
        except (KeyboardInterrupt, EOFError):
            return False
        return answer.strip().lower() in ("y", "yes")

    @staticmethod
    def _tool_to_spec(tool: Tool) -> ToolSpec:
        return ToolSpec(
            name=tool.name,
            description=tool.description,
            parameters=tool.params_schema,
        )

    @staticmethod
    def _serialize_tool_result(result: ToolResult) -> str:
        """Сериализуем ToolResult для отправки обратно в LLM."""
        data: dict[str, Any] = {
            "success": result.success,
            "output": result.output,
        }
        if result.error:
            data["error"] = result.error
        return json.dumps(data, ensure_ascii=False)
