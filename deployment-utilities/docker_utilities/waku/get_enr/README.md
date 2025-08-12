## Waku ENR Fetcher Script

This Bash script retrieves and validates the ENRs 
of Waku nodes in a Kubernetes deployment. 
It queries a given service name to obtain pod IPs, 
then extracts and verifies the ENR 
from each node's debug API. 
The valid ENRs are saved in an environment file for further use.

It is intended to be used when we need to have ENR
to set up waku configuration flags like 
[discv5](https://docs.waku.org/guides/nwaku/config-options/#discv5-config).
In order to grab random ENRs, we rely on kubernetes services.
For example, we assign every discv5 bootstrap node to a service for bootstrap nodes, 
and then we use this container to retrieve their ENRs.

### Usage:
```
./getenr.sh [NUM_ENRS] [SERVICE_NAME]
```

### Arguments:
- `NUM_ENRS` (optional) – The number of ENRs to retrieve. 
Defaults to `3` if not specified.
- `SERVICE_NAME` (optional) – The Kubernetes service name
to query for pod IPs. Defaults to `zerotesting-bootstrap.zerotesting`.

### Example in Kubernetes yaml
```
initContainers:
  - name: grabenr
    image: <your-registry>/getenr:v1.0.0
    imagePullPolicy: IfNotPresent
    volumeMounts:
      - name: enr-data
        mountPath: /etc/enr
    command:
      - /app/getenr.sh
    args:
      - "3"

...

command:
  - sh
  - -c
  - |
    . /etc/enr/enr.env
    echo ENRs are $ENR1 $ENR2 $ENR3
    /usr/bin/wakunode --discv5-bootstrap-node=$ENR1
```


### How It Works
1. **Fetch Pod IPs**: Uses nslookup to find the IPv4 addresses
of the specified service.
2. **Query Each Pod**: Sends an HTTP request 
to each pod at port `8645`, 
retrieving the enrUri from its debug API.
3. **Validate Addresses**: Ensures that the retrieved ENR
start with `enr:`, indicating a valid ENR format.
4. **Store Valid Addresses**: Saves valid addresses
as environment variables in `/etc/enr/enr.env`.

### Output
If successful, the script stores addresses in `/etc/addrs/addrs.env`
as environment variables:
```
export enr1='enr:-MS4QGcHBZAnpu6qNYe_T6TGDCV6c9_3UsXlj5XlXY6QvLCUQKqajqDfs0aKOs7BISJzGxA7TuDzYXap4sP6JYUZ2Y9GAYh2F0dG5ldHOIAAAAAAAAAACEZXRoMpEJZZp0BAAAAf__________gmlkgnY0gmlwhC5QoeSJc2VjcDI1NmsxoQOZxJYJVoTfwo7zEom6U6L5Txrs3H9X0P_XBJbbOZBczYYN1ZHCCdl8'
```

