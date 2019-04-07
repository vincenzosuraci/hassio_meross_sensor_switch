# hassio_meross_sensor_switch
A Home Assistant custom-component for Meross devices, based 
on the work done by [Alberto Geniola](https://github.com/albertogeniola/MerossIot) and [Chris Hurst](https://github.com/hurstc/hassio-meross)

Devices
============

Tested only with my [mss310](https://www.meross.com/product/6/article/) and 
[mss210](https://www.meross.com/product/3/article/) version 2.0.0 smart outlets.
```
Currently, the Smart WiFi Surge Protectors (e.g. MSS425E) are not supported.
``` 
However, refer to [Alberto Geniola](https://github.com/albertogeniola/MerossIot) for the full compatibility list.

Install
============

- **Copy all the files (except README.md) into /config/custom_components/meross directory**
```
copy all the files but README.md into your "/config/custom_components/meross" folder.
- create the /custom_components/meross directories, if needed 
- the meross_iot framework will be downloaded automatically)
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

