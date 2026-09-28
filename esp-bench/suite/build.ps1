# Build kopie ESPTest v pracovni slozce benchmarku.
# ESP-IDF v5.2.6 jako robot; export.ps1 + idf.py jako build() v ESPTest\release.py.
# Z Git Bashe idf.py primo nejede, proto pres PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
# Vypis: BUILD OK/FAILED, pocet varovani, u chyby konec logu. Cely log je v build.log.

$ErrorActionPreference = "Continue"
# Spusteno z Git Bashe (tak to dela i Claude Code) zdedi MSYSTEM a ESP-IDF pak
# odmitne bezet: "MSys/Mingw is not supported".
Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
$idf = Join-Path $env:USERPROFILE "esp\v5.2.6\esp-idf"
. (Join-Path $idf "export.ps1") *> $null

Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot "build.log"
$bin = Join-Path $PSScriptRoot "build\esptest.bin"

if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    Write-Output "BUILD FAILED: ESP-IDF prostredi se nenacetlo (export.ps1)"
    [IO.File]::WriteAllText($log, "ESP-IDF prostredi se nenacetlo`n")
    exit 2
}

# Smazat .bin i .elf: build musi vysledek vyrobit znovu, jinak by mohl projit se starym.
# Samotny .bin nestaci, ninja by pri nezmenenych zdrojich .elf nelinkoval a .bin nevytvoril.
Remove-Item $bin, (Join-Path $PSScriptRoot "build\esptest.elf") -ErrorAction SilentlyContinue
$out = @(& idf.py --ccache build 2>&1 | ForEach-Object { "$_" })
$code = $LASTEXITCODE
[IO.File]::WriteAllLines($log, [string[]]$out)

$warnings = @($out | Where-Object { $_ -match "warning:" })
if ($code -eq 0 -and (Test-Path $bin)) {
    Write-Output "BUILD OK, varovani: $($warnings.Count)"
} else {
    if ($code -eq 0) { $code = 3 }
    Write-Output "BUILD FAILED (exit $code), varovani: $($warnings.Count)"
    $out | Select-Object -Last 40
}
$warnings | Select-Object -First 20
exit $code
