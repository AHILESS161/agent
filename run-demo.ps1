# Запуск демо-стенда одной командой (Windows PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File run-demo.ps1
#
# Скрипт готовит базу (миграции, демо-данные, индексация базы знаний)
# и поднимает backend (8000) и frontend (3000) в двух окнах.
# Данные демонстрационные, реальная подача заявки в Роспатент отключена.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Не найден venv. Создаю и ставлю зависимости..." -ForegroundColor Yellow
    python -m venv (Join-Path $root "venv")
    & $python -m pip install -r (Join-Path $root "backend\requirements.txt")
}

Push-Location (Join-Path $root "backend")
try {
    Write-Host "`n[1/4] Миграции базы данных..." -ForegroundColor Cyan
    & $python -m alembic upgrade head

    Write-Host "`n[2/4] Демо-аккаунты без фейковых клиентов и заявок..." -ForegroundColor Cyan
    & $python -m app.seed.init_db

    Write-Host "`n[3/4] Индексация базы знаний (нужна для правового анализа)..." -ForegroundColor Cyan
    & $python -m scripts.ingest_knowledge
}
finally {
    Pop-Location
}

Write-Host "`n[4/4] Запуск сервисов..." -ForegroundColor Cyan

# Backend и frontend поднимаются в отдельных окнах, чтобы их логи
# было видно и чтобы закрыть каждый по отдельности.
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\backend'; & '$python' -m uvicorn app.main:app --port 8000 --host 127.0.0.1"
)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\frontend'; if (-not (Test-Path node_modules)) { npm ci }; " +
    "`$env:VITE_API_URL='http://localhost:8000'; npm run dev"
)

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host " Интерфейс:  http://localhost:3000" -ForegroundColor Green
Write-Host " API-доки:   http://localhost:8000/docs" -ForegroundColor Green
Write-Host "----------------------------------------------------------------" -ForegroundColor Green
Write-Host " Вход (любой из):" -ForegroundColor Green
Write-Host "   lawyer@demo.ru  / demo123   — специалист (юрист)"
Write-Host "   bogdan@demo.ru  / demo123   — юрист Богдан"
Write-Host "   dasha@demo.ru   / demo123   — юрист Даша"
Write-Host "   manager@demo.ru / demo123   — менеджер"
Write-Host "   admin@demo.ru   / demo123   — администратор"
Write-Host "================================================================`n" -ForegroundColor Green
Write-Host "Сервисы открылись в двух отдельных окнах. Закройте их, чтобы остановить стенд."
