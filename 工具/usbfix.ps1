
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$log = "C:\Users\Zzy\AppData\Local\Temp\opencode\usbfix.log"
"=== USB ghost device cleanup $(Get-Date) ===" | Out-File $log -Encoding utf8
# 1) 列出所有非正常状态的 Espressif / 描述符失败设备
$ghosts = Get-PnpDevice | Where-Object { $_.Status -eq 'Unknown' -and ($_.InstanceId -like 'USB\VID_303A*' -or $_.InstanceId -like 'USB\VID_0000*') }
foreach ($g in $ghosts) {
    "Removing: $($g.InstanceId)  [$($g.FriendlyName)]" | Out-File $log -Append -Encoding utf8
    pnputil /remove-device $g.InstanceId 2>&1 | Out-File $log -Append -Encoding utf8
}
# 2) 重新扫描
pnputil /scan-devices 2>&1 | Out-File $log -Append -Encoding utf8
Start-Sleep -Seconds 3
# 3) 汇报当前串口
"=== Current serial ports ===" | Out-File $log -Append -Encoding utf8
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Name | Out-File $log -Append -Encoding utf8
