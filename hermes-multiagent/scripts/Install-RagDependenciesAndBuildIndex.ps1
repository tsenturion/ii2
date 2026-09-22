# Устанавливает зависимости RAG и строит локальный индекс проекта.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirementsPath = Join-Path $projectRoot "rag-requirements.txt"
$buildIndexPath = Join-Path $projectRoot "rag\build_index.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Не найден Python виртуального окружения: $pythonPath"
}

if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Не найден файл зависимостей RAG: $requirementsPath"
}

if (-not (Test-Path -LiteralPath $buildIndexPath -PathType Leaf)) {
    throw "Не найден индексатор RAG: $buildIndexPath"
}

Write-Warning "Будут загружены sentence-transformers, PyTorch и embedding-модель. Это может занять продолжительное время и потребовать значительный объём диска."

& $pythonPath -m pip install -r $requirementsPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $pythonPath $buildIndexPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
