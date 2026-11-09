# Build the single-file exe (工作计划 4.5). Run from anywhere: pwsh packaging/build_exe.ps1
# Output: dist/agentboxbox_<version>.exe, version taken from boxbox/__init__.py (#57).
# Needs: pip install pyinstaller pystray pywebview   (pillow comes with pystray)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $name = (python packaging\version_info.py name).Trim()
    python packaging\version_info.py file build\version_info.txt | Out-Null
    python packaging\runtime.py build\runtime              # #81：node.exe + Pi bundle，exe 开箱即用
    if ($LASTEXITCODE -ne 0) { throw "runtime staging failed" }
    python packaging\licenses.py --check                  # 第三方许可清单要和这次打进去的东西一致
    if ($LASTEXITCODE -ne 0) { throw "THIRD_PARTY_LICENSES.txt 过期：python packaging\licenses.py 后提交" }
    # 只为可选功能被顺带收进来的包（PIL / bottle / PyInstaller 自己的可选 import），exe 用不到，也不在许可清单里
    $excl = 'numpy','psutil','cryptography','bcrypt','jinja2','markupsafe','yaml','setuptools','pkg_resources','threadpoolctl','charset_normalizer','defusedxml','olefile','PyInstaller','altgraph','pefile','ordlookup','win32ctypes','packaging','tkinter' | ForEach-Object { '--exclude-module', $_ }
    $args = @(
        '--noconfirm', '--clean', '--onefile', '--noconsole', '--name', $name,
        '--version-file', "$root\build\version_info.txt",
        '--distpath', 'dist', '--workpath', 'build/pyi', '--specpath', 'build',
        '--add-data', "$root\build\runtime;runtime",
        '--add-data', "$root\boxbox\static;boxbox\static",
        '--add-data', "$root\boxbox\templates;boxbox\templates",
        '--add-data', "$root\boxbox\connectors.json;boxbox",
        '--add-data', "$root\boxbox\providers.json;boxbox",   # #80：models.dev 服务商清单快照
        '--add-data', "$root\static;static",
        '--add-data', "$root\office\office.html;office",   # 只带运行时要的两个文件：拼装源码、截图不进 exe
        '--add-data', "$root\office\build\cats.js;office\build",
        '--add-data', "$root\assets\icon;assets\icon",
        '--add-data', "$root\LICENSE;.", '--add-data', "$root\THIRD_PARTY_NOTICES.md;.",   # 许可和隐私声明随 exe 走，设置页能打开
        '--add-data', "$root\THIRD_PARTY_LICENSES.txt;.", '--add-data', "$root\PRIVACY.md;.",
        '--add-data', "$root\PRIVACY.en.md;.", '--add-data', "$root\THIRD_PARTY_NOTICES.en.md;.",   # 英文界面的声明
        '--icon', "$root\assets\icon\boxbox.ico",
        '--collect-submodules', 'pystray',
        '--collect-all', 'webview',
        '--hidden-import', 'PIL.Image', '--hidden-import', 'PIL.ImageDraw'
    ) + $excl + @('packaging\entry.py')
    python -m PyInstaller @args
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller exit $LASTEXITCODE" }
    python packaging\licenses.py --verify-toc "build\pyi\$name\PYZ-00.toc"
    if ($LASTEXITCODE -ne 0) { throw "exe 里有许可清单没列的包" }
    $exe = Join-Path $root "dist\$name.exe"
    # dist 里只留这一个 exe：旧版本留着会被人拷错（拷到旧 exe，打开还是旧向导）
    Get-ChildItem dist -Filter *.exe | Where-Object { $_.FullName -ne $exe } | ForEach-Object {
        $old = $_
        try { Remove-Item $old.FullName -Force -ErrorAction Stop; "removed old: $($old.Name)" }
        catch { Write-Warning "旧的 $($old.Name) 删不掉（可能还开着），记得别拷它" }
    }
    "built: $exe  ($([math]::Round((Get-Item $exe).Length / 1MB, 1)) MB)  version $((Get-Item $exe).VersionInfo.ProductVersion)"
} finally { Pop-Location }
