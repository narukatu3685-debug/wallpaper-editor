# デスクトップに「壁紙加工ツール」のショートカットを作る（setup.bat から呼ばれる）。
# パスはこのスクリプトの場所から求めるので、どのフォルダに置いても動く。
$root = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop '壁紙加工ツール.lnk'))
$lnk.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$lnk.Arguments = '"' + (Join-Path $root 'run_app.pyw') + '"'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = Join-Path $root 'app_icon.ico'
$lnk.Save()
Write-Host "Shortcut created: $desktop\壁紙加工ツール.lnk"
