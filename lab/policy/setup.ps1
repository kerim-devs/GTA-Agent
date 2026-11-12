# Builds everything the policy model needs under one folder of the account gta, which can be removed
# as a whole: uv, a Python of its own, torch with CUDA, NitroGen at a pinned commit and its weights
# (about 6 GB over the network). Nothing is installed for the machine and nothing starts by itself.
# Only the packages of the server are installed: the repository's default set would pull in vgamepad,
# which installs a driver. Running it again skips what is there.
$root = "C:\Users\gta\policy"
New-Item -ItemType Directory -Force -Path $root | Out-Null
Set-Location $root
$env:UV_PYTHON_INSTALL_DIR = "$root\python"
$env:UV_CACHE_DIR = "$root\cache"
$env:HF_HOME = "$root\hf"
$env:UV_LINK_MODE = "copy"
function Run { & $args[0] $args[1..($args.Length-1)]; if ($LASTEXITCODE -ne 0) { throw "failed ($LASTEXITCODE): $args" } }
if (-not (Test-Path "$root\uv\uv.exe")) {
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile "$root\uv.zip"
  Expand-Archive -Force "$root\uv.zip" "$root\uv"
}
$uv = "$root\uv\uv.exe"
Run $uv --version
if (-not (Test-Path "$root\venv")) { Run $uv venv "$root\venv" --python 3.11 --quiet }
$py = "$root\venv\Scripts\python.exe"
$sha = "32608444660950ffda95e1e57c79632ad65bea10"
if (-not (Test-Path "$root\NitroGen-$sha")) {
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/MineDojo/NitroGen/archive/$sha.zip" -OutFile "$root\nitrogen.zip"
  Expand-Archive -Force "$root\nitrogen.zip" $root
}
Run $uv pip install --quiet --python $py torch --index-url https://download.pytorch.org/whl/cu124
Run $uv pip install --quiet --python $py numpy pyzmq pyyaml einops transformers pydantic diffusers polars pillow huggingface_hub
if (-not (Test-Path "$root\ng.pt")) {
  Run $py -c "from huggingface_hub import hf_hub_download; print(hf_hub_download('nvidia/NitroGen', 'ng.pt', local_dir=r'C:\Users\gta\policy'))"
}
Run $py -c "import torch, transformers, numpy; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0), '| transformers', transformers.__version__, '| numpy', numpy.__version__)"
Run $uv pip freeze --python $py | Out-File -Encoding utf8 "$root\freeze.txt"
Get-ChildItem $root | ForEach-Object { "{0,12:N0}  {1}" -f $(if ($_.PSIsContainer) { 0 } else { $_.Length }), $_.Name }
