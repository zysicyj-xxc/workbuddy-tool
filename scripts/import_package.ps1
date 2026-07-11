# 导入 .enc 到本地实例
param(
  [Parameter(Mandatory = $true)][string]$EncFile,
  [switch]$Replace
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path $EncFile)) {
  Write-Error "文件不存在: $EncFile"
}

# 读取 .env 中的口令（简单解析）
$Password = "workbuddy-change-me"
$Port = "8000"
$AuthUser = "admin"
$AuthPass = ""
if (Test-Path .env) {
  Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*DATA_PACKAGE_PASSWORD=(.*)$') { $Password = $Matches[1].Trim() }
    if ($_ -match '^\s*APP_PORT=(.*)$') { $Port = $Matches[1].Trim() }
    if ($_ -match '^\s*BASIC_AUTH_USER=(.*)$') { $AuthUser = $Matches[1].Trim() }
    if ($_ -match '^\s*BASIC_AUTH_PASSWORD=(.*)$') { $AuthPass = $Matches[1].Trim() }
  }
}

$form = @{
  file     = Get-Item -Path $EncFile
  password = $Password
  replace  = if ($Replace) { "true" } else { "false" }
}

$headers = @{}
if ($AuthPass) {
  $pair = "{0}:{1}" -f $AuthUser, $AuthPass
  $bytes = [Text.Encoding]::ASCII.GetBytes($pair)
  $headers["Authorization"] = "Basic " + [Convert]::ToBase64String($bytes)
}

$uri = "http://127.0.0.1:${Port}/api/data/import-encrypted"
$resp = Invoke-RestMethod -Uri $uri -Method Post -Form $form -Headers $headers
$resp | ConvertTo-Json -Depth 5
Write-Host "[ok] 导入完成"
