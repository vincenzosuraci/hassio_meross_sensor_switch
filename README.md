# hassio_meross_sensor_switch
A Home Assistant custom-component for Meross devices, based 
on the work done by [Alberto Geniola](https://github.com/albertogeniola/MerossIot) and [Chris Hurst](https://github.com/hurstc/hassio-meross)

Devices
============

Tested only with my mss310 and mss210 version 2.0.0 smart outlets.
However, refer to [Alberto Geniola](https://github.com/albertogeniola/MerossIot) for the full compatibility list.

Install
============

- **Copy custom_components folder into your config directory**
```
copy "custom_components" folder into your "/config" folder.
(the meross_iot framework will be downloaded automatically)
```

Configuration
============

- **For mss310 and mss210 v2.0.0 devices, change some lines of codes in the merioss_iot component**
```
replace the "power_plug.py" file with the one provided in my library.
In a RPi/hassio installation, it is located in "\config\deps\lib\python3.7\site-packages\meross_iot\supported_devices" folder
```

- **Add your credentials to configuration.yaml**
```
meross:
  username: !secret meross_userame
  password: !secret meross_password

# I added these lines to prevent some frequent log status messages I noticed
logger:
  logs:
    meross_powerplug: warning

