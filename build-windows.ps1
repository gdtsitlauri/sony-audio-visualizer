param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m pip install -U pyinstaller
pyinstaller --noconfirm --clean "Sony Visualizer.spec"

$exePath = Join-Path $root "dist\Sony Visualizer.exe"
if (-not (Test-Path $exePath)) {
    throw "Build failed: '$exePath' not found."
}

if (-not [string]::IsNullOrWhiteSpace($Version)) {
    $tag = $Version.Trim()
    $outName = "Sony-Visualizer-$tag-windows-x64.exe"
    $outPath = Join-Path $root ("dist\" + $outName)
    Copy-Item -LiteralPath $exePath -Destination $outPath -Force
    Write-Host "Build complete: $outPath"
} else {
    Write-Host "Build complete: $exePath"
}
