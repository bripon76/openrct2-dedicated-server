# openrct2-dedicated-server
This is a docker container, that is capable of running a [OpenRCT2](http://openrct2.org/) server in a headless mode (dedicated Server).

## Edit config file
You will need a `config.ini` file mounted to the host to run the game properly.

Make sure that `game_path` is set to this value: 

```
...
game_path = "/openrct2/original_files"
...
```

You'll want to configure your server info:

```
...
[network]
player_name = "server" 
default_password = "password"
advertise = true
maxplayers = 16
server_name = "headless-server"
server_description = ""
server_greeting = ""
master_server_url = ""
provider_name = ""
provider_email = ""
provider_website = ""
known_keys_only = false
log_chat = true
...
```

## Run the container
To run the container you need to mount the config file, the original game files and the save game / scenario you want to run.  The paths inside the container are:

- `/openrct2/original_files/`: the directory on the orginal game files
- `/root/.config/OpenRCT2/`: folder that contains the config.ini file. Will also be the directory for auto-saves, chatlogs, group and user settings.
- `/openrct2/game.sc6`: the savegame the server is running

The container runs the OpenRCT2 server and exposes the port `11753`. You have to map it to any port on the host.

```shell
docker run -p <PORT>:11753 -v <GAME_FOLDER>:/openrct2/original_files/ -v <CONFIG_FOLDER>:/root/.config/OpenRCT2/ -v <SAVEGAME>:/openrct2/game.sc6 snowmb/openrct2docker:latest
```

## Set privileges
The provided `groups.json` file specifies `admin` as default privilege. You should change that after connecting to the server.


