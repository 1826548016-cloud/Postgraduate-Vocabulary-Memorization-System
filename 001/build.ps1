# 一键打包脚本
# 用法（PowerShell）：
#     cd d:\word\001
#     .\build.ps1
# 产物：d:\word\001\dist\word\word.exe
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$specFile = Join-Path $PSScriptRoot 'word.spec'

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '  考研英语学习平台 - 打包脚本' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan

# 1. 检查 PyInstaller
$pyinstaller = & pip show pyinstaller 2>$null | Select-String 'Name:'
if (-not $pyinstaller) {
    Write-Host '[1/4] 安装 PyInstaller…' -ForegroundColor Yellow
    pip install pyinstaller
} else {
    Write-Host '[1/4] PyInstaller 已安装' -ForegroundColor Green
}

# 2. 检查项目依赖
Write-Host '[2/4] 检查项目依赖…' -ForegroundColor Yellow
pip install -r (Join-Path $projectRoot 'requirements.txt') --quiet

# 3. 清理旧产物
Write-Host '[3/4] 清理旧产物…' -ForegroundColor Yellow
$buildDir = Join-Path $PSScriptRoot 'build'
$distDir = Join-Path $PSScriptRoot 'dist'
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }

# 4. 打包
Write-Host '[4/4] 开始打包（约 1-3 分钟）…' -ForegroundColor Yellow
Push-Location $PSScriptRoot
try {
    pyinstaller $specFile --noconfirm
} finally {
    Pop-Location
}

$exePath = Join-Path $distDir 'word\word.exe'
if (Test-Path $exePath) {
    Write-Host ''
    Write-Host '========================================================' -ForegroundColor Green
    Write-Host '  打包成功！' -ForegroundColor Green
    Write-Host "  产物：$exePath" -ForegroundColor Green
    Write-Host '  双击 word.exe 即可运行。' -ForegroundColor Green
    Write-Host '========================================================' -ForegroundColor Green
} else {
    Write-Host '打包失败，请查看上方日志。' -ForegroundColor Red
    exit 1
}
