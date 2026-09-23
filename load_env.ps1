# load_env.ps1 — загружает .env в текущий процесс как переменные окружения.
# Используется из OSA_Telegram_Bot.cmd.

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "[OSA Bot] .env не найден: $envFile"
    exit 1
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    if ($line -match '^([^=]+)=(.*)$') {
        $key = $Matches[1].Trim()
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

Write-Host "[OSA Bot] .env loaded OK"
exit 0
