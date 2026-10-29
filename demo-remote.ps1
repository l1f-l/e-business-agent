# ============================================================
#  ShopPilot 本地演示 · 内网穿透一键启动
#  用法：双击 demo-remote.bat（或右键本文件 → 使用 PowerShell 运行）
#  作用：起后端(8000) + 前端(3000) + Cloudflare 隧道，输出公网链接
# ============================================================

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$backend  = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$toolsDir = Join-Path $root "tools"
$cfExe    = Join-Path $toolsDir "cloudflared.exe"
$cfErr    = Join-Path $toolsDir "tunnel.log"
$cfOut    = Join-Path $toolsDir "tunnel.out.log"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Head($msg) { Write-Host ""; Write-Host "=== $msg ===" -ForegroundColor Cyan }

function PortOpen($port) {
  $client = New-Object Net.Sockets.TcpClient
  try {
    $iar = $client.BeginConnect("127.0.0.1", $port, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne(600)) { return $false }
    $client.EndConnect($iar)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

Write-Host ""
Say "ShopPilot · 演示环境启动中（Ctrl+C 可中断）" "White"
Say "项目目录：$root" "DarkGray"

# ---------- 1. 后端 ----------
Head "1/3 后端 :8000"
if (PortOpen 8000) {
  Say "端口 8000 已有服务，跳过启动" "DarkGray"
} else {
  $py = Join-Path $backend ".venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    Say "找不到虚拟环境：$py" "Red"
    Say "请先在 backend 目录执行：python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" "Yellow"
    Read-Host "按回车退出"
    exit 1
  }
  Start-Process -FilePath $py `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") `
    -WorkingDirectory $backend -WindowStyle Minimized
  Say "已启动（最小化窗口，关掉它后端就停了）" "Green"
}

# ---------- 2. 前端 ----------
Head "2/3 前端 :3000"
if (PortOpen 3000) {
  Say "端口 3000 已有服务，跳过启动" "DarkGray"
} else {
  Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev -- -H 0.0.0.0 -p 3000" `
    -WorkingDirectory $frontend -WindowStyle Minimized
  Say "已启动，等待编译..." "Green"
  Write-Host "   " -NoNewline
  $deadline = (Get-Date).AddSeconds(150)
  while (-not (PortOpen 3000) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1500
    Write-Host "." -NoNewline
  }
  Write-Host ""
  if (-not (PortOpen 3000)) {
    Say "前端 150 秒内没起来，请查看那个最小化的窗口里的报错" "Red"
    Read-Host "按回车退出"
    exit 1
  }
}

# 触发一次首页编译，免得同事打开时等太久
Say "预热首页..." "DarkGray"
try {
  Invoke-WebRequest "http://127.0.0.1:3000/" -UseBasicParsing -TimeoutSec 120 | Out-Null
  Say "首页已编译完成" "Green"
} catch {
  Say "预热失败（不影响使用）：$($_.Exception.Message)" "DarkYellow"
}

# ---------- 3. 内网穿透 ----------
Head "3/3 公网穿透"

if (-not (Test-Path $cfExe)) {
  if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir | Out-Null }
  $ProgressPreference = "SilentlyContinue"
  $rel = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  $mirrors = @($rel, "https://ghproxy.net/$rel", "https://gh-proxy.com/$rel")
  $got = $false
  foreach ($m in $mirrors) {
    if ($got) { break }
    Say "下载 cloudflared ... $m" "DarkGray"
    try {
      Invoke-WebRequest $m -OutFile $cfExe -UseBasicParsing -TimeoutSec 300
      if ((Get-Item $cfExe).Length -gt 5MB) {
        Say "下载完成（$([math]::Round((Get-Item $cfExe).Length / 1MB, 1)) MB）" "Green"
        $got = $true
      } else {
        Remove-Item $cfExe -Force -ErrorAction SilentlyContinue
      }
    } catch {
      Say "失败：$($_.Exception.Message)" "DarkYellow"
      Remove-Item $cfExe -Force -ErrorAction SilentlyContinue
    }
  }
  if (-not $got) {
    Say "" 
    Say "自动下载失败，请手动下载 cloudflared-windows-amd64.exe：" "Red"
    Say "  https://github.com/cloudflare/cloudflared/releases/latest" "Yellow"
    Say "保存到：$cfExe" "Yellow"
    Read-Host "按回车退出"
    exit 1
  }
}

function New-TunnelProcess($argList) {
  try {
    return Start-Process -FilePath $cfExe -ArgumentList $argList `
      -RedirectStandardError $cfErr -RedirectStandardOutput $cfOut -NoNewWindow -PassThru -ErrorAction Stop
  } catch {
    # 部分环境同时设了 HTTPS_PROXY 和 https_proxy，Windows 视为重名，Start-Process 会抛异常
    foreach ($n in @("http_proxy", "https_proxy", "no_proxy", "all_proxy")) {
      try { Remove-Item ("Env:" + $n) -ErrorAction SilentlyContinue } catch { }
    }
    return Start-Process -FilePath $cfExe -ArgumentList $argList `
      -RedirectStandardError $cfErr -RedirectStandardOutput $cfOut -NoNewWindow -PassThru
  }
}

function Start-Tunnel($extra) {
  Remove-Item $cfErr -Force -ErrorAction SilentlyContinue
  Remove-Item $cfOut -Force -ErrorAction SilentlyContinue
  $argList = @("tunnel", "--url", "http://127.0.0.1:3000", "--no-autoupdate") + $extra
  $proc = New-TunnelProcess $argList
  $u = $null
  $dl = (Get-Date).AddSeconds(50)
  while (-not $u -and (Get-Date) -lt $dl) {
    Start-Sleep -Seconds 1
    if (Test-Path $cfErr) {
      $t = Get-Content $cfErr -Raw -ErrorAction SilentlyContinue
      # 排除 https://api.trycloudflare.com（失败时的报错里也会出现，会误判成建立成功）
      if ($t -match "https://(?!api\.)[A-Za-z0-9\-]+\.trycloudflare\.com") { $u = $Matches[0] }
    }
    if ($proc.HasExited) { break }
  }
  return [pscustomobject]@{ Proc = $proc; Url = $u }
}

$protocol = @()
$round = 0
while ($true) {
  $round++
  if ($round -gt 1) { Write-Host ""; Say "重新建立隧道（第 $($round - 1) 次重连）..." "Yellow" }

  $try = Start-Tunnel $protocol
  if (-not $try.Url -and $protocol.Count -eq 0) {
    Say "QUIC 没连上，改用 http2 重试（部分公司网络会拦 UDP）..." "DarkYellow"
    try { Stop-Process -Id $try.Proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    Start-Sleep -Seconds 2
    $protocol = @("--protocol", "http2")
    $try = Start-Tunnel $protocol
  }
  if (-not $try.Url) {
    Say "隧道没建立起来，10 秒后重试。检查：本机能否上网 / 是否拦了 Cloudflare 出站。" "Red"
    try { Stop-Process -Id $try.Proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    Start-Sleep -Seconds 10
    continue
  }

  $tunnel = $try.Proc
  $url = $try.Url

  Write-Host ""
  Say "隧道已建立，正在从公网回连自检..." "DarkGray"
  # 先等 cloudflared 真正注册上边缘节点（日志出现 Registered ...），否则域名还没生效
  $regDl = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $regDl) {
    if (Test-Path $cfErr) {
      $logText = Get-Content $cfErr -Raw -ErrorAction SilentlyContinue
      if ($logText -match "Registered tunnel connection") { break }
    }
    Start-Sleep -Milliseconds 800
  }
  $alive = $false
  $detail = ""
  $curlExe = Join-Path $env:SystemRoot "System32\curl.exe"
  $dl2 = (Get-Date).AddSeconds(60)
  while (-not $alive -and (Get-Date) -lt $dl2) {
    if (Test-Path $curlExe) {
      # curl 自带完整 TLS 栈，且 --noproxy 能绕开系统/机场代理，最能反映同事的真实访问
      $code = (& $curlExe -s --noproxy "*" -o NUL -w "%{http_code}" --max-time 15 $url 2>$null)
      $detail = "HTTP $code"
      if ("$code" -match '^[23]') { $alive = $true } else { Start-Sleep -Seconds 2 }
    } else {
      try {
        $resp = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 15
        $detail = "HTTP $($resp.StatusCode)"
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { $alive = $true } else { Start-Sleep -Seconds 2 }
      } catch { $detail = $_.Exception.Message; Start-Sleep -Seconds 2 }
    }
  }
  if ($alive) { Say "自检通过（$detail）：外网已经能正常打开" "Green" }
  else {
    Say "自检没通过（$detail）" "Yellow"
    Say "先用本机浏览器打开 http://localhost:3000 确认服务正常；只要本机能开，链接通常也能用。" "Yellow"
  }

  try { Set-Clipboard -Value $url } catch { }
  Say "==================================================" "Green"
  Say "  公网地址（已复制到剪贴板，直接粘给同事）" "Green"
  Say "  $url" "Cyan"
  Say "==================================================" "Green"
  Say "同事用手机 4G 或家里电脑都能打开，无需同 WiFi。" "White"
  Say "演示账号：u1001 / shop1234（自带 2 笔订单，方便演示查单）" "White"
  Say "本窗口保持开启；掉线会自动重连（重连后链接会变，会重新打印）。" "Yellow"
  Say "链接是随机的，每次重启都会变，演示前现场发最新链接。" "Yellow"
  Write-Host ""

  # 守护：进程退出，或公网连续 4 次（20 秒一次）访问不通 → 重新建隧道
  $fail = 0
  while ($true) {
    Start-Sleep -Seconds 20
    if ($tunnel.HasExited) { Say "隧道进程已退出。" "Yellow"; break }
    $probe = (& $curlExe -s --noproxy "*" -o NUL -w "%{http_code}" --max-time 10 $url 2>$null)
    if ("$probe" -match '^[23]') { $fail = 0 }
    else {
      $fail++
      Say "公网探测失败（$fail/4）：HTTP $probe" "DarkGray"
    }
    if ($fail -ge 4) { Say "公网连续 4 次访问不通，判定链路已断。" "Yellow"; break }
  }
  try { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue } catch { }
  Start-Sleep -Seconds 3
}
