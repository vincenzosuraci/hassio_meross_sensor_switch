# hassio_meross_sensor_switch
- A Home Assistant custom-component for Meross devices, based 
on the work done by [Alberto Geniola](https://github.com/albertogeniola/MerossIot) and [Chris Hurst](https://github.com/hurstc/hassio-meross)
- This custom-component adds the switch and sensor capabilities of your Meross device in Home Assistant

Devices
============

Tested only with my [mss310](https://www.meross.com/product/6/article/) and 
[mss210](https://www.meross.com/product/3/article/) version 2.0.0 smart outlets.
However, refer to [Alberto Geniola](https://github.com/albertogeniola/MerossIot) for the full compatibility list.


Install
============

- **Copy all the ".py" files into your "/config/custom_components/meross" folder.**
1. Your configuration should look like:
```
config
  custom_components
    meross
      __init__.py
      sensor.py
      switch.py
```
2. Reboot Hassio or Home Assistant
Note that the meross_iot framework will be downloaded automatically.

Configuration
============

- **Add your credentials to configuration.yaml**
- username and password are mandatory
- scan_interval is optional. It must be a positive integer number. It represents the seconds between two consecutive scans to gather new values of Meross devices' sensors and switches. 
- meross_devices_scan_interval is optional. It must be a positive integer number. It represents the minutes between two consecutive scans to update the list of available Meross devices. 
```
meross:
  username: !secret meross_userame
  password: !secret meross_password
  scan_interval: 10
  meross_devices_scan_interval: 5

