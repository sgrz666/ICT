param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("doctor", "bootstrap", "up", "test", "smoke", "benchmark", "down")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$Profile = "screening"
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir -and $MyInvocation.MyCommand.Path) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $ScriptDir -and $MyInvocation.MyCommand.Definition) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}
if (-not $ScriptDir) {
    $ScriptDir = Join-Path (Get-Location).Path "scripts"
}
$WorkspaceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$EduForgeDir = Join-Path $WorkspaceRoot "code\eduforge"
$PyVenv = Join-Path $EduForgeDir ".venv"
$PythonExe = Join-Path $PyVenv "Scripts\python.exe"
$PytestExe = Join-Path $PyVenv "Scripts\pytest.exe"
$NodeModules = Join-Path $EduForgeDir "node_modules"
$PidFile = Join-Path $WorkspaceRoot "output\eduforge\eduforge.pids"

function Check-PortAvailable([int]$Port) {
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

function Start-EduForgeService([string]$FileName, [string]$Arguments, [string]$WorkingDirectory, [hashtable]$EnvVars) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    $psi.Arguments = $Arguments
    if ($WorkingDirectory) { $psi.WorkingDirectory = $WorkingDirectory }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    if ($EnvVars) {
        foreach ($k in $EnvVars.Keys) {
            $psi.EnvironmentVariables[$k] = [string]$EnvVars[$k]
        }
    }
    return [System.Diagnostics.Process]::Start($psi)
}


function Stop-ProcessTree([int]$ParentId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree $child.ProcessId
    }
    Stop-Process -Id $ParentId -Force -ErrorAction SilentlyContinue
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
        Write-Host "=== Starting EduForge Full System Services ===" -ForegroundColor Cyan

        # 1. 检查构建产物
        $webDistFile = Join-Path $EduForgeDir "apps\teacher-web\dist\index.html"
        $engineDistFile = Join-Path $EduForgeDir "services\engine-host\dist\main.js"
        if (-not (Test-Path $webDistFile) -or -not (Test-Path $engineDistFile)) {
            Write-Host "Bootstrap artifacts missing. Running bootstrap first..." -ForegroundColor Yellow
            & (Join-Path $ScriptDir "eduforge.ps1") bootstrap
        }

        # 2. 检查端口占用
        $free8000 = Check-PortAvailable 8000
        $free8010 = Check-PortAvailable 8010
        $free4174 = Check-PortAvailable 4174
        if (-not $free8010) { Write-Host "Error: Port 8010 (Engine Host) is already in use." -ForegroundColor Red; exit 1 }
        if (-not $free4174) { Write-Host "Error: Port 4174 (Browser Gateway) is already in use." -ForegroundColor Red; exit 1 }
        if (-not $free8000) { Write-Host "Error: Port 8000 (API Backend) is already in use." -ForegroundColor Red; exit 1 }

        $outDir = Join-Path $WorkspaceRoot "output\eduforge"
        if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
        $artDir = Join-Path $outDir "artifacts"
        if (-not (Test-Path $artDir)) { New-Item -ItemType Directory -Path $artDir -Force | Out-Null }
        $pgDataDir = Join-Path $outDir "pgdata"
        $uriFile = Join-Path $outDir "pg_uri.txt"

        $pids = @()

        # 3. 启动数据库 (Postgres via run_db.py)
        Write-Host "`n[1/4] Starting PostgreSQL database..." -ForegroundColor Yellow
        if (Test-Path $uriFile) { Remove-Item $uriFile -Force -ErrorAction SilentlyContinue }
        $dbProc = Start-EduForgeService $PythonExe "tools/run_db.py --data-dir `"$pgDataDir`" --uri-file `"$uriFile`"" $EduForgeDir $null
        $pids += $dbProc.Id
        Write-Host ("  PostgreSQL started with PID " + $dbProc.Id) -ForegroundColor Green

        # 等待 URI 文件就绪
        $dbUri = ""
        $timeout = 30
        while ($timeout -gt 0) {
            if (Test-Path $uriFile) {
                $dbUri = (Get-Content $uriFile -Raw).Trim()
                if ($dbUri) { break }
            }
            Start-Sleep -Milliseconds 500
            $timeout--
        }
        if (-not $dbUri) {
            Write-Host "Error: Failed to obtain PostgreSQL URI within timeout." -ForegroundColor Red
            & (Join-Path $ScriptDir "eduforge.ps1") down
            exit 1
        }
        Write-Host ("  Database URI: " + $dbUri) -ForegroundColor Cyan

        # 4. 启动业务 API (FastAPI / uvicorn)
        Write-Host "`n[2/4] Starting API backend (FastAPI :8000)..." -ForegroundColor Yellow
        $apiEnv = @{
            "EDUFORGE_DSN" = $dbUri
            "EDUFORGE_ARTIFACT_DIR" = $artDir
        }
        $apiProc = Start-EduForgeService $PythonExe "-m uvicorn eduforge.api.serve:app --host 127.0.0.1 --port 8000 --log-level warning" $EduForgeDir $apiEnv
        $pids += $apiProc.Id
        Write-Host ("  API Backend started with PID " + $apiProc.Id) -ForegroundColor Green

        # 等待 API 端口就绪
        $apiReady = $false
        for ($i = 0; $i -lt 30; $i++) {
            if (-not (Check-PortAvailable 8000)) {
                $apiReady = $true
                break
            }
            Start-Sleep -Milliseconds 400
        }
        if (-not $apiReady) {
            Write-Host "Error: API Backend failed to bind to port 8000." -ForegroundColor Red
            & (Join-Path $ScriptDir "eduforge.ps1") down
            exit 1
        }

        # 5. 启动 Engine Host 与 Browser Gateway (Node)
        Write-Host "`n[3/4] Starting Engine Host (:8010) and Browser Gateway (:4174)..." -ForegroundColor Yellow
        $engineHostDir = Join-Path $EduForgeDir "services\engine-host"
        $teacherWebDist = Join-Path $EduForgeDir "apps\teacher-web\dist"
        $nodeEnv = @{
            "ENGINE_HOST_PORT" = "8010"
            "ENGINE_GATEWAY_PORT" = "4174"
            "EDUFORGE_API_URL" = "http://127.0.0.1:8000"
            "EDUFORGE_TEACHER_WEB_DIST" = $teacherWebDist
        }
        $nodeProc = Start-EduForgeService "node" "dist/main.js" $engineHostDir $nodeEnv
        $pids += $nodeProc.Id
        Write-Host ("  Engine Host & Gateway started with PID " + $nodeProc.Id) -ForegroundColor Green

        # 等待 8010 和 4174 就绪
        for ($i = 0; $i -lt 30; $i++) {
            if (-not (Check-PortAvailable 8010) -and -not (Check-PortAvailable 4174)) { break }
            Start-Sleep -Milliseconds 400
        }

        # 6. 启动 Worker 进程
        Write-Host "`n[4/4] Starting EduForge Worker..." -ForegroundColor Yellow
        $workerArgsStr = "-m eduforge.worker.run --dsn `"$dbUri`" --engine-url http://127.0.0.1:8010 --artifact-dir `"$artDir`""

        # 解析 DeepSeek API Key（优先支持 $env:deepseek，并自动回填 $env:DEEPSEEK_API_KEY）
        $deepseekKey = $env:deepseek
        if (-not $deepseekKey) { $deepseekKey = $env:DEEPSEEK }
        if (-not $deepseekKey) { $deepseekKey = $env:DEEPSEEK_API_KEY }
        if (-not $deepseekKey) {
            $deepseekKey = [System.Environment]::GetEnvironmentVariable("deepseek", "User")
        }
        if (-not $deepseekKey) {
            $deepseekKey = [System.Environment]::GetEnvironmentVariable("deepseek", "Machine")
        }
        if (-not $deepseekKey) {
            $deepseekKey = [System.Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
        }
        if (-not $deepseekKey) {
            $deepseekKey = [System.Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "Machine")
        }

        # 规划器选择：默认 deep（Deep Agents 自主循环），可用 EDUFORGE_PLANNER=model|deep|static 覆盖。
        # 没有 key 时**不再**自动塞 --planner-static-focal：那会让一次链路演练
        # 看起来像模型产出，正是上一版把「静态提案」当成「Agent 能力」的源头。
        $plannerKind = if ($env:EDUFORGE_PLANNER) { $env:EDUFORGE_PLANNER } else { "deep" }

        if ($deepseekKey) {
            $env:deepseek = $deepseekKey
            $env:DEEPSEEK_API_KEY = $deepseekKey
            Write-Host "  [OK] DeepSeek API key loaded from environment (value not printed)" -ForegroundColor Green
            if ($plannerKind -eq "static") {
                $workerArgsStr += " --planner-static-focal 15"
            } else {
                $workerArgsStr += " --planner $plannerKind"
            }
        } elseif ($env:EDUFORGE_ALLOW_STATIC_PLANNER -eq "1") {
            $workerArgsStr += " --planner-static-focal 15"
            Write-Host "  [警告] 无 key，且显式允许 static：Worker 用命令行注入的固定提案跑链路。" -ForegroundColor DarkYellow
            Write-Host "         这只验证任务链路与交付，不构成任何 Agent 规划能力的证据。" -ForegroundColor DarkYellow
        } else {
            Write-Host "  [错误] 未检测到 DeepSeek 密钥，Worker 不会用固定提案冒充模型产出。" -ForegroundColor Red
            Write-Host "         配置密钥后再启动；或设 EDUFORGE_ALLOW_STATIC_PLANNER=1 明确只做链路验证。" -ForegroundColor Red
            return
        }
        $workerProc = Start-EduForgeService $PythonExe $workerArgsStr $EduForgeDir $null
        $pids += $workerProc.Id
        Write-Host ("  Worker started with PID " + $workerProc.Id) -ForegroundColor Green

        # 记录所有 PID
        $pids | Out-File -FilePath $PidFile -Encoding ascii

        Write-Host "`n========================================================" -ForegroundColor Green
        Write-Host " EduForge & Ray Optics 全系统一键启动成功！" -ForegroundColor Green
        Write-Host "  综合工作台 (Web UI): http://127.0.0.1:4174/" -ForegroundColor Cyan
        Write-Host "  ⚡ Ray Optics 原生模拟器直开: http://127.0.0.1:4174/simulator/?zh-CN" -ForegroundColor Cyan
        Write-Host "  📚 81个交互演示案例库: http://127.0.0.1:4174/cn/gallery/" -ForegroundColor Cyan
        Write-Host "  业务 API 文档 (Swagger): http://127.0.0.1:8000/docs" -ForegroundColor Cyan
        Write-Host "  仿真引擎宿主 (Engine Host): http://127.0.0.1:8010/healthz" -ForegroundColor Cyan
        Write-Host "  停止全部服务请运行: .\scripts\eduforge.ps1 down" -ForegroundColor Yellow
        Write-Host "========================================================`n" -ForegroundColor Green
        exit 0
    }

    "down" {
        Write-Host "=== Stopping EduForge Services ===" -ForegroundColor Cyan

        # 1. 优先优雅停止 PostgreSQL，防止 WAL/log 崩溃状态
        $pgDataDir = Join-Path $WorkspaceRoot "output\eduforge\pgdata"
        if (Test-Path $pgDataDir) {
            $pgCtl = Join-Path $EduForgeDir ".venv\Lib\site-packages\pgserver\pginstall\bin\pg_ctl.exe"
            $pidPath = Join-Path $pgDataDir "postmaster.pid"
            if ((Test-Path $pgCtl) -and (Test-Path $pidPath)) {
                cmd /c "`"$pgCtl`" -D `"$pgDataDir`" stop -m fast >nul 2>nul"
                Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
            }
        }

        # 2. 停止记录在 PID 文件的服务
        if (Test-Path $PidFile) {
            $pids = Get-Content $PidFile
            foreach ($p in $pids) {
                if ($p -match "^\d+$") {
                    Write-Host ("Stopping PID " + $p + " and child processes") -ForegroundColor Yellow
                    Stop-ProcessTree ([int]$p)
                }
            }
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host "No running PID recorded." -ForegroundColor DarkGray
        }

        # 3. 补充清理子进程或可能残留的端口进程
        $cleanPorts = @(8000, 8010, 4174)
        foreach ($port in $cleanPorts) {
            $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
            foreach ($c in $conns) {
                if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
                    Write-Host ("Cleaning residual process on port " + $port + " (PID " + $c.OwningProcess + ")") -ForegroundColor Yellow
                    Stop-ProcessTree $c.OwningProcess
                }
            }
        }

        $uriFile = Join-Path $WorkspaceRoot "output\eduforge\pg_uri.txt"
        if (Test-Path $uriFile) { Remove-Item $uriFile -Force -ErrorAction SilentlyContinue }

        Write-Host "All EduForge services stopped cleanly." -ForegroundColor Green
        exit 0
    }
}
