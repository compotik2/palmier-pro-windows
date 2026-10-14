$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "venv failed" }
    }
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }
    & ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    & ".\.venv\Scripts\python.exe" scripts/build.py
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    $process = Start-Process -FilePath ".\dist\PalmierProWindows\PalmierProWindows.exe" -ArgumentList '--verify-media', '--output', "$PSScriptRoot\test-output\packaged-media.json" -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Packaged media validation failed" }
} finally {
    Pop-Location
}
