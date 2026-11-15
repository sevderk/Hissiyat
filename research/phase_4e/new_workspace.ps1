$ErrorActionPreference = 'Stop'
$local = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$base = Join-Path $local 'Hissiyat'
$workspace = Join-Path $base ('phase-4e-' + [guid]::NewGuid().ToString('N'))
$repo = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '../..')).FullName.TrimEnd('\') + '\'
if ($workspace.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.DriveInfo]::new([IO.Path]::GetPathRoot($workspace)).DriveType -ne 'Fixed') {
    throw 'Unexpected private workspace location.'
}
for ($parent = [IO.DirectoryInfo]::new($local); $null -ne $parent; $parent = $parent.Parent) {
    if (-not $parent.Exists -or ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Unexpected LocalAppData path.'
    }
}
$syncRoots = @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial,
    (Join-Path $env:USERPROFILE 'Dropbox'), (Join-Path $env:USERPROFILE 'Google Drive'),
    (Join-Path $env:USERPROFILE 'iCloudDrive'))
foreach ($provider in (Get-ChildItem -LiteralPath 'HKCU:\Software\SyncEngines\Providers' -ErrorAction SilentlyContinue)) {
    foreach ($entry in (Get-ChildItem -LiteralPath $provider.PSPath -ErrorAction SilentlyContinue)) {
        $syncRoots += (Get-ItemProperty -LiteralPath $entry.PSPath -Name MountPoint -ErrorAction SilentlyContinue).MountPoint
    }
}
foreach ($path in $syncRoots) {
    if ($path -and [IO.Path]::IsPathFullyQualified($path) -and
        $workspace.StartsWith(([IO.Path]::GetFullPath($path).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Private workspace falls under a known sync root.'
    }
}
[void][IO.Directory]::CreateDirectory($base)
if (((Get-Item -LiteralPath $base -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    (Test-Path -LiteralPath $workspace)) {
    throw 'Unexpected private workspace path.'
}
$directory = New-Item -ItemType Directory -Path $workspace
try {
    $owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [IO.FileSystemAclExtensions]::GetAccessControl($directory)
    $acl.SetOwner($owner)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($entry in $acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier])) {
        $acl.RemoveAccessRuleSpecific($entry)
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $owner, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'
    ))
    [IO.FileSystemAclExtensions]::SetAccessControl($directory, $acl)
    $workspace
} catch {
    [IO.Directory]::Delete($workspace)
    throw
}
