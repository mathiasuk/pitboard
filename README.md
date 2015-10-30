# pitboard

Pitboard is all about removing the clutter from your screen, and showing you whatt you need, when you need it, while trying to be realistic with a touch of eye candy.

There are two modes depending on the session: race or practice/quali.

In quali mode the pitboard will show up each time you pass the start finish line. The board will display your current position in the standings, the name of the driver ahead in the standing and the delta**, as well as your last laptime and delta, and finally the time left in the session.

In race mode the board will display your current position and number of laps left, the car ahead and behind along with their delta, (and the delta compared to the previous lap).

Contrary to most apps (such as my own [actracker](https://github.com/mathiasuk/actracker)), pitboard doesn't estimate the delta between cars, but actually splits the track in 10 seconds and meaures actual delta time at each sector, this means that the delta showns are not dependent on the track section, and much more similar to what you get in actual racing.

By default the pitboard is displayed in full size for 15 seconds after the start/finish line, after which it scales down to a smaller version for another 30 seconds. This can be changed by clicking the settings icon on the left of the title. You can also set it to use short names instead of full names (e.g.: FAN instead of FANGIO), as well as showing a detailed delta or not during the race). These settings are saved and remembered across session.

** caveat: when joining a session in progress Assetto Corsa doesn't provide the best laptimes for each car. Pitboard does its best to get the best laptimes from other cars as they happen, but it works better if you join quali session from the get go.
