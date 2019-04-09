# hassio_meross_sensor_switch
- A Home Assistant custom-component for Meross devices, based 
on the work done by [Alberto Geniola](https://github.com/albertogeniola/MerossIot) and [Chris Hurst](https://github.com/hurstc/hassio-meross)
- This custom-component adds the switch and sensor capabilities of your Meross device in Home Assistant

Devices
============

Tested only with my [mss310](https://www.meross.com/product/6/article/) and 
[mss210](https://www.meross.com/product/3/article/) version 2.0.0 smart outlets.
However, refer to [Alberto Geniola](https://github.com/albertogeniola/MerossIot) for the full compatibility list.
```
Currently, the Smart WiFi Surge Protectors (e.g. MSS425E) are not supported.
``` 

Install
============

- **Copy all the files, but README.md, into your "/config/custom_components/meross" folder.**
- Your configuration should look like:
```
config
  custom_components
    meross
      __init__.py
      sensor.py
      switch.py
```
- The meross_iot framework will be downloaded automatically.

Configuration
============

- **Add your credentials to configuration.yaml**
- username and password are mandatory
- scan_interval is optional. It must be a positive integer number. It represents the seconds between two consecutive scans.
Consider that decreasing its value, means that the home assistant custom component will query the Meross cloud service more frequently to gather the status of all the connected devices. Consider that the time required to obtain a response from the Meross cloud can vary from few seconds to decades of seconds, especially if you have many Meross connected devices. The default value is 30 seconds. 
```
meross:
  username: !secret meross_userame
  password: !secret meross_password
  scan_interval: 30

