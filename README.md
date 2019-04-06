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

- **Add your credentials to configuration.yaml**
```
meross:
  username: !secret meross_userame
  password: !secret meross_password

# Add these lines to prevent frequent log from meross_iot library
logger:
  logs:
    meross_powerplug: warning

