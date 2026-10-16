param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("doctor", "bootstrap", "up", "test", "smoke", "benchmark", "down")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$Profile = "screening"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$WorkspaceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$EduForgeDir = Join-Path $WorkspaceRoot "code\eduforge"
$PyVenv = Join-Path $EduForgeDir ".venv"
$PythonExe = Join-Path $PyVenv "Scripts\python.exe"
$PytestExe = Join-Path $PyVenv "Scripts\pytest.exe"
$NodeModules = Join-Path $EduForgeDir "node_modules"
$PidFile = Join-Path $WorkspaceRoot "output\eduforge\eduforge.pids"

function Check-PortAvailable([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -eq $connections)
}

switch ($Action) {
    "doctor" {
        Write-Host "=== EduForge Doctor Checklist ===" -ForegroundColor Cyan
        $allPassed = $true

        if (Test-Path $PythonExe) {
            $pyVer = & $PythonExe --version 2>&1
            Write-Host ("  [OK] Python: " + $pyVer) -ForegroundColor Green
        } else {
            Write-Host ("  [FAIL] Python not found in venv: " + $PythonExe) -ForegroundColor Red
            $allPassed = $false
        }

        try {
            $nodeVer = node --version 2>&1
            Write-Host ("  [OK] Node.js: " + $nodeVer) -ForegroundColor Green
        } catch {
            Write-Host "  [FAIL] Node.js not found" -ForegroundColor Red
            $allPassed = $false
        }

        $upstreamCore = Join-Path $WorkspaceRoot "source\upstream\ray-optics\dist-node\rayOptics.js"
        if (Test-Path $upstreamCore) {
            $sz = (Get-Item $upstreamCore).Length
            Write-Host ("  [OK] Ray Optics Core: dist-node/rayOptics.js (" + $sz + " bytes)") -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Ray Optics core not built" -ForegroundColor Yellow
        }

        try {
            $dockerInfo = docker info 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  [OK] Docker: daemon running" -ForegroundColor Green
            } else {
                Write-Host "  [INFO] Docker Desktop not running (using pgserver for Postgres 16.2)" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "  [INFO] Docker not installed (using pgserver for Postgres 16.2)" -ForegroundColor DarkGray
        }

        $p8000 = Check-PortAvailable 8000
        $p8010 = Check-PortAvailable 8010
        if ($p8000) {
            Write-Host "  [OK] Port 8000 (API): Available" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Port 8000 (API): In use" -ForegroundColor Yellow
        }
        if ($p8010) {
            Write-Host "  [OK] Port 8010 (Gateway/Preview): Available" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Port 8010 (Gateway/Preview): In use" -ForegroundColor Yellow
        }

        $catalogLens = Join-Path $EduForgeDir "catalog\templates\optics\convex-lens\manifest.yaml"
        if (Test-Path $catalogLens) {
            Write-Host "  [OK] Catalog: optics.convex_lens manifest present" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Catalog: manifest missing" -ForegroundColor Red
            $allPassed = $false
        }

        if ($allPassed) {
            Write-Host "`nDoctor passed: Environment is healthy." -ForegroundColor Green
            exit 0
        } else {
            Write-Host "`nDoctor failed: Please fix reported FAIL items." -ForegroundColor Red
            exit 1
        }
    }

    "bootstrap" {
        Write-Host "=== EduForge Bootstrap ===" -ForegroundColor Cyan
        if (-not (Test-Path $PythonExe)) {
            Write-Host "Creating virtual environment..." -ForegroundColor Yellow
            python -m venv $PyVenv
        }
        
        $teacherDist = Join-Path $EduForgeDir "apps\teacher-web\dist\index.html"
        if (-not (Test-Path $teacherDist)) {
            Write-Host "Building apps/teacher-web..." -ForegroundColor Yellow
            Push-Location (Join-Path $EduForgeDir "apps\teacher-web")
            npm run build
            Pop-Location
        } else {
            Write-Host "  [OK] Teacher web built" -ForegroundColor Green
        }

        $engineDist = Join-Path $EduForgeDir "services\engine-host\dist\main.js"
        if (-not (Test-Path $engineDist)) {
            Write-Host "Building services/engine-host..." -ForegroundColor Yellow
            Push-Location (Join-Path $EduForgeDir "services\engine-host")
            npm run build
            Pop-Location
        } else {
            Write-Host "  [OK] Engine Host built" -ForegroundColor Green
        }

        Write-Host "Bootstrap complete." -ForegroundColor Green
        exit 0
    }

    "test" {
        Write-Host "=== Running EduForge Test Suite ===" -ForegroundColor Cyan
        
        Write-Host "`n[1/2] Running Python pytest suite..." -ForegroundColor Yellow
        Push-Location $EduForgeDir
        & $PytestExe
        $pyExit = $LASTEXITCODE
        Pop-Location

        if ($pyExit -ne 0) {
            Write-Host ("Python tests failed with exit code " + $pyExit) -ForegroundColor Red
            exit $pyExit
        }

        Write-Host "`n[2/2] Running Node vitest suite..." -ForegroundColor Yellow
        Push-Location (Join-Path $EduForgeDir "services\engine-host")
        node node_modules/vitest/vitest.mjs run
        $nodeExit = $LASTEXITCODE
        Pop-Location

        if ($nodeExit -ne 0) {
            Write-Host ("Vitest failed with exit code " + $nodeExit) -ForegroundColor Red
            exit $nodeExit
        }

        Write-Host "`nAll tests passed successfully!" -ForegroundColor Green
        exit 0
    }

    "smoke" {
        Write-Host "=== Running End-to-End Browser Smoke Test ===" -ForegroundColor Cyan
        Push-Location $EduForgeDir
        & $PytestExe tests/python/test_teacher_web_e2e.py
        $smokeExit = $LASTEXITCODE
        Pop-Location
        exit $smokeExit
    }

    "benchmark" {
        Write-Host ("=== Running Benchmarks (Profile: " + $Profile + ") ===") -ForegroundColor Cyan
        Push-Location $EduForgeDir
        & $PythonExe benchmarks/runner.py --profile $Profile
        $benchExit = $LASTEXITCODE
        Pop-Location
        exit $benchExit
    }

    "up" {
        Write-Host "=== Starting EduForge Local Services ===" -ForegroundColor Cyan
        if (-not (Check-PortAvailable 8010)) {
            Write-Host "Error: Port 8010 is already in use." -ForegroundColor Red
            exit 1
        }

        $engineHostDir = Join-Path $EduForgeDir "services\engine-host"
        $proc = Start-Process node -ArgumentList "dist/main.js" -WorkingDirectory $engineHostDir -PassThru -NoNewWindow
        
        $outDir = Split-Path -Parent $PidFile
        if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
        $proc.Id | Out-File -FilePath $PidFile -Encoding ascii

        Write-Host ("Engine Host and Gateway started with PID " + $proc.Id) -ForegroundColor Green
        Write-Host "  Web UI URL: http://127.0.0.1:8010/" -ForegroundColor Cyan
        exit 0
    }

    "down" {
        Write-Host "=== Stopping EduForge Services ===" -ForegroundColor Cyan
        if (Test-Path $PidFile) {
            $pids = Get-Content $PidFile
            foreach ($p in $pids) {
                if ($p -match "^\d+$") {
                    $proc = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
                    if ($proc) {
                        Write-Host ("Stopping PID " + $p + " (" + $proc.ProcessName + ")") -ForegroundColor Yellow
                        Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
                    }
                }
            }
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host "No running PID recorded." -ForegroundColor DarkGray
        }
        Write-Host "Services stopped. Database and artifact data preserved." -ForegroundColor Green
        exit 0
    }
}
