# 解密 PC 微信加密的 wxapkg（头部 "V1MMWX"）
# 用法: pwsh -File tools/decrypt_wxapkg.ps1 -In <__APP__.wxapkg> -AppId wxXXXXXXXX -Out unpacked/__APP__.wxapkg
param(
    [Parameter(Mandatory=$true)][string]$In,
    [Parameter(Mandatory=$true)][string]$AppId,
    [Parameter(Mandatory=$true)][string]$Out
)

$data = [System.IO.File]::ReadAllBytes($In)
if ([System.Text.Encoding]::ASCII.GetString($data[0..5]) -ne "V1MMWX") {
    throw "不是 V1MMWX 加密包，直接用 unpack_wxapkg.py"
}

$headLen = 1024
$salt = [System.Text.Encoding]::UTF8.GetBytes("saltiest")
$kdf  = [System.Security.Cryptography.Rfc2898DeriveBytes]::new($AppId, $salt, 1000, [System.Security.Cryptography.HashAlgorithmName]::SHA1)
$key  = $kdf.GetBytes(32)
$iv   = [System.Text.Encoding]::ASCII.GetBytes("the iv: 16 bytes.")

$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
$aes.Padding = [System.Security.Cryptography.PaddingMode]::None
$aes.Key = $key
$aes.IV = $iv
$dec = $aes.CreateDecryptor()

$head = $data[0..($headLen-1)]
$plainHead = $dec.TransformFinalBlock($head, 0, $head.Length)

# 剩余部分整体单字节异或，密钥用文件头特征反推
$xorKey = -1
for ($k = 0; $k -lt 256; $k++) {
    if (($data[$headLen] -bxor $k) -eq 0xBE -and ($data[$headLen+13] -bxor $k) -eq 0xED) { $xorKey = $k; break }
}
if ($xorKey -lt 0) { throw "找不到异或密钥，包结构异常" }

$rest = New-Object byte[] ($data.Length - $headLen)
[Array]::Copy($data, $headLen, $rest, 0, $rest.Length)
for ($i = 0; $i -lt $rest.Length; $i++) { $rest[$i] = $rest[$i] -bxor $xorKey }

$outBytes = New-Object byte[] ($plainHead.Length + $rest.Length)
[Array]::Copy($plainHead, 0, $outBytes, 0, $plainHead.Length)
[Array]::Copy($rest, 0, $outBytes, $plainHead.Length, $rest.Length)

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
[System.IO.File]::WriteAllBytes($Out, $outBytes)

"解密完成: xorKey=0x{0:X2}  head=0x{1:X2}  size={2} -> {3}" -f $xorKey, $outBytes[0], $outBytes.Length, $Out
