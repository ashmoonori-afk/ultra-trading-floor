$ErrorActionPreference = "Stop"

$limit = 250
$failed = $false

Get-ChildItem -Path "src", "tests" -Filter "*.py" -Recurse | ForEach-Object {
    $count = (Get-Content -LiteralPath $_.FullName | Where-Object {
        $_ -notmatch '^\s*$' -and $_ -notmatch '^\s*#'
    }).Count
    Write-Output "$($_.FullName): $count"
    if ($count -gt $limit) {
        $failed = $true
    }
}

if ($failed) {
    exit 1
}
