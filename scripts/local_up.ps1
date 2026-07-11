# 本地空库启动（Windows PowerShell）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "[ok] 已生成 .env（请按需修改口令）"
}

docker compose up -d --build
Write-Host ""
Write-Host "服务已启动: http://localhost:8000"
Write-Host "空库导入: .\scripts\import_package.ps1 .\your-backup.enc"
