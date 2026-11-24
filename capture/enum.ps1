$ErrorActionPreference = 'SilentlyContinue'
Write-Output "=== PnP devices with VID_046D (Logitech) ==="
Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_046D' } | ForEach-Object {
  "{0} | {1} | {2} | {3}" -f $_.Status, $_.Class, $_.FriendlyName, $_.InstanceId
}
Write-Output ""
Write-Output "=== Bluetooth devices (Logitech / MX) ==="
Get-PnpDevice -Class Bluetooth | Where-Object { $_.FriendlyName -match 'Logitech|MX|Master' } | ForEach-Object {
  "{0} | {1} | {2}" -f $_.Status, $_.FriendlyName, $_.InstanceId
}
Write-Output ""
Write-Output "=== USB devices (Logitech) ==="
Get-PnpDevice -Class USB | Where-Object { $_.FriendlyName -match 'Logitech|Unifying' -or $_.InstanceId -match 'VID_046D' } | ForEach-Object {
  "{0} | {1} | {2}" -f $_.Status, $_.FriendlyName, $_.InstanceId
}
