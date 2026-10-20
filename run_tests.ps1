param(
    [string]$Suite = "smoke",
    [string]$Config = "config.json"
)
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    if (!(Test-Path ".env")) { throw "Copy .env.example to .env and fill your local server settings." }
    if (!(Test-Path $Config)) { throw "Copy config.example.json to config.json first." }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 benchmark.py --config $Config --suite $Suite
    } else {
        & python benchmark.py --config $Config --suite $Suite
    }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
