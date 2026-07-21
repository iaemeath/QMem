# V4.0 目录拆分：覆盖三个 MCP server 进程
# - QMem:          mcp/qmem/server.py
# - DomainKG:      mcp/domain-kg/server.py
# - codebase-memory: mcp/codebase-memory/codebase-memory-mcp.exe
$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'qmem[\\/]server\.py|domain-kg[\\/]server\.py|codebase-memory[\\/]codebase-memory-mcp'
}
foreach ($p in $processes) {
    Write-Host "Killing Process ID: $($p.ProcessId) - $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force
}
Write-Host "Done."
