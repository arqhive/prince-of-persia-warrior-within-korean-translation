#Requires -Version 5.1
param(
    [Parameter(Position = 0)][string]$Source,
    [Parameter(Position = 1)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$buffer = New-Object byte[] (8MB)
$data = Join-Path $PSScriptRoot 'data'
$bin = Join-Path $PSScriptRoot 'bin'
$formats = @('.iso', '.gcm', '.ciso', '.wia', '.wdf', '.gcz')

function Read-U32([byte[]]$Bytes, [int]$At) {
    return (([long]$Bytes[$At] -shl 24) -bor ([long]$Bytes[$At + 1] -shl 16) -bor
        ([long]$Bytes[$At + 2] -shl 8) -bor $Bytes[$At + 3])
}

function Read-Bytes($Stream, [long]$Start, [int]$Length) {
    if ($Start -lt 0 -or $Length -lt 0 -or $Start + $Length -gt $Stream.Length) {
        throw '디스크의 파일 범위가 이미지 크기를 벗어납니다.'
    }
    $bytes = New-Object byte[] $Length
    $Stream.Position = $Start
    $done = 0
    while ($done -lt $Length) {
        $read = $Stream.Read($bytes, $done, $Length - $done)
        if ($read -eq 0) { throw '이미지가 중간에서 잘렸습니다.' }
        $done += $read
    }
    return ,$bytes
}

function Copy-Range($From, $To, [long]$Offset, [long]$Length) {
    $From.Position = $Offset
    while ($Length -gt 0) {
        $read = $From.Read($buffer, 0, [int][Math]::Min($Length, $buffer.Length))
        if ($read -eq 0) { throw '게임 파일이 중간에서 잘렸습니다.' }
        $To.Write($buffer, 0, $read)
        $Length -= $read
    }
}

function Add-Range($Ranges, [long]$Start, [long]$Length, [long]$Bound) {
    if ($Start -lt 0 -or $Length -lt 0 -or $Start + $Length -gt $Bound) {
        throw '이미지 크기가 작거나 게임 파일 위치가 잘못되었습니다.'
    }
    if ($Length -gt 0) {
        $Ranges.Add([pscustomobject]@{ Start = $Start; End = $Start + $Length })
    }
}

function Read-Layout($Disc, $Config) {
    $header = Read-Bytes $Disc 0 0x2460
    $id = [Text.Encoding]::ASCII.GetString($header, 0, 6)
    if ($id -cne $Config.id -or $header[6] -ne 0 -or $header[7] -ne [int]$Config.rev) {
        throw "지원하는 북미판 G2OE41 리비전 0이 아닙니다. 읽은 게임 ID ($id), 리비전 ($($header[7]))."
    }
    if ((Read-U32 $header 0x1c) -ne 0xc2339f3dL) { throw '게임큐브 원본 이미지가 아닙니다.' }
    $dol = Read-U32 $header 0x420
    $fst = Read-U32 $header 0x424
    $fstSize = Read-U32 $header 0x428
    $fstCapacity = [Math]::Max($fstSize, (Read-U32 $header 0x42c))
    if ($fstSize -lt 12 -or $fstSize -gt 16MB) { throw '파일 목록(FST) 크기가 잘못되었습니다.' }
    $appEnd = 0x2460 + (Read-U32 $header 0x2454) + (Read-U32 $header 0x2458)
    $dolHeader = Read-Bytes $Disc $dol 0x100
    if ((Read-U32 $dolHeader 0x08) -ne 0 -or (Read-U32 $dolHeader 0x98) -ne 0) {
        throw '원본 게임 실행 파일이 다릅니다. 패치 전 북미판 원본을 사용하세요.'
    }
    $dolSize = 0x100L
    for ($i = 0; $i -lt 18; $i++) {
        $size = Read-U32 $dolHeader (0x90 + 4 * $i)
        if ($size -gt 0) {
            $offset = Read-U32 $dolHeader (4 * $i)
            if ($offset -lt 0x100) { throw '게임 실행 파일의 섹션 위치가 잘못되었습니다.' }
            $dolSize = [Math]::Max($dolSize, $offset + $size)
        }
    }

    $table = Read-Bytes $Disc $fst $fstSize
    $count = Read-U32 $table 8
    if ($table[0] -ne 1 -or $count -lt 2 -or 12 * $count -gt $fstSize) {
        throw '원본의 파일 목록(FST)을 읽을 수 없습니다.'
    }
    $ranges = New-Object 'System.Collections.Generic.List[object]'
    Add-Range $ranges 0 $appEnd $Disc.Length
    Add-Range $ranges $dol $dolSize $Disc.Length
    Add-Range $ranges $fst $fstCapacity $Disc.Length
    $directories = New-Object 'System.Collections.Generic.List[object]'
    $directories.Add(@{ Name = ''; End = $count })
    $files = @{}
    for ($i = 1; $i -lt $count; $i++) {
        while ($i -ge $directories[$directories.Count - 1].End) {
            $directories.RemoveAt($directories.Count - 1)
        }
        $parent = $directories[$directories.Count - 1]
        $at = 12 * $i
        $entry = Read-U32 $table $at
        $offset = Read-U32 $table ($at + 4)
        $size = Read-U32 $table ($at + 8)
        $start = 12 * $count + ($entry -band 0xffffff)
        if ($start -ge $fstSize) { throw '파일 이름 위치가 잘못되었습니다.' }
        $stop = [Array]::IndexOf($table, [byte]0, [int]$start)
        if ($stop -le $start) { throw '파일 이름이 잘못되었습니다.' }
        $name = $parent.Name + '/' + [Text.Encoding]::ASCII.GetString($table, [int]$start, [int]($stop - $start))
        if (($entry -shr 24) -eq 1) {
            if ($size -le $i -or $size -gt $parent.End) { throw '폴더 범위가 잘못되었습니다.' }
            $directories.Add(@{ Name = $name; End = $size })
        } elseif (($entry -shr 24) -eq 0) {
            if ($files.ContainsKey($name)) { throw "파일 목록에 중복 항목이 있습니다. ($name)" }
            Add-Range $ranges $offset $size $Disc.Length
            $files[$name] = @{ Start = $offset; Size = $size }
        } else { throw '지원하지 않는 파일 목록 항목입니다.' }
    }
    $ranges = @($ranges | Sort-Object -Property Start, End)
    $last = 0L
    foreach ($range in $ranges) {
        if ($range.Start -lt $last) { throw '게임 파일 영역이 서로 겹칩니다.' }
        $last = $range.End
    }
    return @{ Dol = $dol; DolSize = $dolSize; FstEnd = $fst + $fstCapacity; Files = $files; Ranges = $ranges }
}

function Find-HookOffset($Layout, [long]$Size, [long]$Limit) {
    $first = [Math]::Max($Layout.Dol + $Layout.DolSize, $Layout.FstEnd)
    $start = ($first + 511) -band (-512L)
    foreach ($range in $Layout.Ranges) {
        if ($start + $Size -le $range.Start) { return $start }
        if ($start -lt $range.End) { $start = ($range.End + 511) -band (-512L) }
    }
    if ($start + $Size -gt $Limit) { throw '한글 글자 처리 코드를 넣을 빈 영역이 없습니다.' }
    return $start
}

function Invoke-LocalTool([string]$Name, [string[]]$Arguments) {
    & (Join-Path $bin $Name) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Name 실행에 실패했습니다. (종료 코드 $LASTEXITCODE)" }
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead((Join-Path $scratch $Path))
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '')
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Apply-File($Disc, $Entry, [long]$Offset, [long]$Size) {
    if ($Size -ne [long]$Entry.size -or $Entry.delta -cnotmatch '^\d{3}\.xdelta$') {
        throw "원본 게임 파일의 크기 또는 패치 목록이 다릅니다. ($($Entry.path))"
    }
    $source = [IO.File]::Create((Join-Path $scratch 'source.bin'))
    try {
        if ($Entry.kind -eq 'hook') {
            $source.SetLength($Size)
        } else {
            Copy-Range $Disc $source $Offset $Size
        }
    } finally { $source.Dispose() }
    if ((Get-Sha256 'source.bin') -ne $Entry.source_sha256) {
        throw "원본 게임 파일이 다릅니다. ($($Entry.path))"
    }
    Copy-Item -LiteralPath (Join-Path $data $Entry.delta) -Destination 'patch.xdelta' -Force
    Invoke-LocalTool 'xdelta3.exe' @('-d', '-f', '-D', '-R', '-s', 'source.bin', 'patch.xdelta', 'patched.bin')
    if ((Get-Item -LiteralPath 'patched.bin').Length -ne $Size -or
        (Get-Sha256 'patched.bin') -ne $Entry.target_sha256) {
        throw "패치한 게임 파일을 검증할 수 없습니다. ($($Entry.path))"
    }
}

if (-not $Source) {
    $candidates = @(Get-ChildItem -LiteralPath $PSScriptRoot -File | Where-Object {
        $_.Extension -in ($formats + '.rvz') -and $_.BaseName -notlike '* (KOR)'
    })
    if ($candidates.Count -ne 1) { throw '원본 이미지 1개를 패치 폴더에 두거나 패치하기.bat 위에 끌어 놓으세요.' }
    $Source = $candidates[0].FullName
}
$inputFile = Get-Item -LiteralPath $Source
$extension = $inputFile.Extension.ToLowerInvariant()
if ($extension -eq '.rvz') { throw 'RVZ는 Dolphin에서 ISO로 변환한 뒤 적용하세요.' }
if ($inputFile.PSIsContainer -or $extension -notin $formats -or
    $inputFile.Name -match '(?i)\.nkit\.' -or $inputFile.BaseName -like '* (KOR)') {
    throw '지원하는 형식의 북미판 원본 이미지를 지정해 주세요. NKit은 원본 ISO로 복원해야 합니다.'
}
if (-not $OutputDirectory) { $OutputDirectory = $inputFile.DirectoryName }
$parent = Get-Item -LiteralPath $OutputDirectory
if (-not $parent.PSIsContainer) { throw '출력 폴더를 지정해 주세요.' }
$output = Join-Path $parent.FullName ($inputFile.BaseName + ' (KOR)' + $inputFile.Extension)
$config = Get-Content -LiteralPath (Join-Path $data 'config.txt') -Raw -Encoding UTF8 | ConvertFrom-StringData
$manifest = @(Import-Csv -LiteralPath (Join-Path $data 'manifest.txt') -Delimiter "`t" -Encoding UTF8)
$dolEntry = @($manifest | Where-Object kind -eq 'dol')
$hookEntry = @($manifest | Where-Object kind -eq 'hook')
$fileEntries = @($manifest | Where-Object kind -eq 'file')
if ($dolEntry.Count -ne 1 -or $hookEntry.Count -ne 1 -or $fileEntries.Count -ne 4 -or $manifest.Count -ne 6) {
    throw '패치 목록 구성이 잘못되었습니다.'
}

$token = [guid]::NewGuid().ToString('N')
$scratch = Join-Path $PSScriptRoot ".popww-patch-$token"
$candidate = Join-Path $parent.FullName (".popww-$token" + $inputFile.Extension)
$oldEnv = @{}
$compressed = $extension -notin @('.iso', '.gcm')
$null = New-Item -ItemType Directory -Path $scratch
try {
    foreach ($var in @('TEMP', 'TMP', 'TMPDIR', 'XDELTA')) {
        $oldEnv[$var] = [Environment]::GetEnvironmentVariable($var, 'Process')
        $value = if ($var -eq 'XDELTA') { $null } else { $scratch }
        [Environment]::SetEnvironmentVariable($var, $value, 'Process')
    }
    Push-Location -LiteralPath $scratch
    try {
        if ($compressed) {
            $container = 'original' + $extension
            [IO.File]::Copy($inputFile.FullName, (Join-Path $scratch $container))
            Invoke-LocalTool 'wit.exe' @('COPY', '--raw', '--iso', $container, 'game.iso')
            Remove-Item -LiteralPath $container
            $raw = Join-Path $scratch 'game.iso'
        } else {
            [IO.File]::Copy($inputFile.FullName, $candidate)
            $raw = $candidate
        }
        $disc = [IO.File]::Open($raw, 'Open', 'ReadWrite', 'None')
        try {
            $limit = [long]$config.disc_size
            if ($disc.Length -lt 0x2460 -or ($disc.Length -gt $limit -and -not $compressed)) {
                throw '이미지 크기를 확인해 주세요.'
            }
            $layout = Read-Layout $disc $config
            if ($layout.Ranges[-1].End -gt $limit) { throw '게임 파일이 게임큐브 디스크 범위를 벗어납니다.' }
            # Container decoders can round the image size up to a full block.
            $hook = Find-HookOffset $layout ([long]$hookEntry[0].size) $limit
            $disc.SetLength($limit)
            foreach ($entry in $fileEntries) {
                $slot = $layout.Files[$entry.path]
                if (-not $slot) { throw "디스크에 필요한 파일이 없습니다. ($($entry.path))" }
                Apply-File $disc $entry $slot.Start $slot.Size
                Write-Host "적용 $($entry.path)"
                $disc.Position = $slot.Start
                $patched = [IO.File]::OpenRead((Join-Path $scratch 'patched.bin'))
                try { $patched.CopyTo($disc) } finally { $patched.Dispose() }
            }
            Apply-File $disc $dolEntry[0] $layout.Dol $layout.DolSize
            $dol = [IO.File]::ReadAllBytes((Join-Path $scratch 'patched.bin'))
            $offset = [BitConverter]::GetBytes([uint32]($hook - $layout.Dol))
            if ([BitConverter]::IsLittleEndian) { [Array]::Reverse($offset) }
            [Array]::Copy($offset, 0, $dol, 8, 4)
            $disc.Position = $layout.Dol
            $disc.Write($dol, 0, $dol.Length)
            Apply-File $disc $hookEntry[0] $hook ([long]$hookEntry[0].size)
            $code = [IO.File]::ReadAllBytes((Join-Path $scratch 'patched.bin'))
            $disc.Position = $hook
            $disc.Write($code, 0, $code.Length)
        } finally { $disc.Dispose() }
        if ($compressed) {
            $container = 'game' + $extension
            $format = if ($extension -eq '.wia') { '--wia=NONE' } else { "--$($extension.Substring(1))" }
            Invoke-LocalTool 'wit.exe' @('COPY', '--raw', $format, 'game.iso', $container)
            [IO.File]::Move((Join-Path $scratch $container), $candidate)
        }
    } finally { Pop-Location }
    if ([IO.File]::Exists($output)) {
        [IO.File]::Replace($candidate, $output, [NullString]::Value)
    } else {
        [IO.File]::Move($candidate, $output)
    }
    Write-Host "패치 완료 $output"
} finally {
    foreach ($var in $oldEnv.Keys) { [Environment]::SetEnvironmentVariable($var, $oldEnv[$var], 'Process') }
    if ([IO.File]::Exists($candidate)) { Remove-Item -LiteralPath $candidate }
    $resolved = (Resolve-Path -LiteralPath $scratch).ProviderPath
    $expectedParent = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
    if ((Split-Path -Parent $resolved) -eq $expectedParent -and (Split-Path -Leaf $resolved) -eq ".popww-patch-$token") {
        Remove-Item -LiteralPath $resolved -Recurse
    }
}
