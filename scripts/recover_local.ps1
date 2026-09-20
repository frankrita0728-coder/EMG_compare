# 一次整理本機 EMG_compare（重新 clone + 只帶回量測檔）
# 用法：在 PowerShell 執行
#   powershell -ExecutionPolicy Bypass -File scripts\recover_local.ps1

$ErrorActionPreference = "Stop"

$Parent = "C:\Zentan_Rita\測試專案"
$OldRepo = Join-Path $Parent "EMG_compare"
$Bak = Join-Path $env:USERPROFILE "Desktop\emg_measure_backup"
$RepoUrl = "https://github.com/frankrita0728-coder/EMG_compare.git"
$Branch = "cursor/feature-correlation-b6d5"

Write-Host "== 1) 備份量測檔到桌面 ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Bak | Out-Null
foreach ($name in @("delsys", "txt", "ZE2_txt")) {
    $src = Join-Path $OldRepo "data\$name"
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src (Join-Path $Bak $name)
        Write-Host "  backed up $name"
    } else {
        Write-Host "  skip missing $name"
    }
}

Write-Host "== 2) 舊資料夾改名保留 ==" -ForegroundColor Cyan
if (Test-Path $OldRepo) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $renamed = "${OldRepo}_舊的混亂版_$stamp"
    Rename-Item $OldRepo $renamed
    Write-Host "  renamed to $renamed"
}

Write-Host "== 3) 重新 clone 乾淨分支 ==" -ForegroundColor Cyan
Set-Location $Parent
git clone -b $Branch $RepoUrl EMG_compare
Set-Location (Join-Path $Parent "EMG_compare")

Write-Host "== 4) 拷回量測檔 ==" -ForegroundColor Cyan
foreach ($name in @("delsys", "txt", "ZE2_txt")) {
    $src = Join-Path $Bak $name
    $dst = Join-Path (Get-Location) "data\$name"
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Copy-Item -Recurse -Force "$src\*" $dst
        Write-Host "  restored $name"
    }
}

Write-Host "== 5) 目前 delsys/2609-09 ==" -ForegroundColor Cyan
Get-ChildItem "data\delsys\2609-09" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }

Write-Host "== 6) 提交並推送量測檔 ==" -ForegroundColor Cyan
git add data/delsys/2609-09/ data/txt/2609-09/ data/ZE2_txt/2609-09/
git status
$pending = git status --porcelain
if (-not $pending) {
    Write-Host "沒有新的量測檔可提交。請確認備份裡有 _with_ZE2_ CSV。" -ForegroundColor Yellow
    exit 0
}
git commit -m "Add local 2609-09 measurement data"
git push origin $Branch
Write-Host "完成。請回 Cloud Agent 說：已推送，請重跑" -ForegroundColor Green
