from vm_manager.constants import USERNAME_PLACEHOLDER, IP_PLACEHOLDER, DOMAIN_PLACEHOLDER

rdp_file = f"""
screen mode id:i:2
session bpp:i:66
compression:i:1
keyboardhook:i:2
displayconnectionbar:i:1
disable wallpaper:i:1
disable full window drag:i:1
allow desktop composition:i:0
allow font smoothing:i:0
disable menu anims:i:1
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
full address:s:{IP_PLACEHOLDER}
audiomode:i:2
microphone:i:0
redirectprinters:i:0
redirectsmartcard:i:0
redirectcomports:i:0
redirectsmartcards:i:0
redirectclipboard:i:1
redirectposdevices:i:0
autoreconnection enabled:i:1
authentication level:i:0
prompt for credentials:i:1
negotiate security layer:i:1
remoteapplicationmode:i:0
alternate shell:s:
shell working directory:s:
gatewayhostname:s:
gatewayusagemethod:i:4
gatewaycredentialssource:i:4
gatewayprofileusagemethod:i:0
precommand:s:
promptcredentialonce:i:1
drivestoredirect:s:
username:s:{USERNAME_PLACEHOLDER}
domain:s:{DOMAIN_PLACEHOLDER}
desktopheight:i:900
desktopwidth:i:1600
connection type:i:7
networkautodetect:i:1
bandwidthautodetect:i:1
"""
