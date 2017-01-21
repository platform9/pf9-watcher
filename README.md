## pf9-watcher

pf9-watcher is python utility to monitor the status of your KVM hypervisors.  If pf9-watcher detects that a host is in the down state, it will evacuate all guest servers from that host

## Installation

```bash
git clone https://github.com/platform9/pf9-watcher.git
pip install ./pf9-watcher
```

## Running Watcher

### Create configuration file

```bash
cd pf9-watcher/pf9watcher
vi watcher_config.ini
```

*watcher_config.ini*

    [keystone]
    endpoint = https://<Controller FQDN>/keystone/v2.0
    username = <username>
    password = <password>
    project_id = service
    region = <region>

    [watcher]
    logfile = watcher.log

### Run watcher service

```bash
python ./watcher.py -c watcher_config.ini
```

