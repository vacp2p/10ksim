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
./getenr.sh [NUM_ENRS] [SERVICE_NAME] [OUTPUT_FILE]
```

### Arguments:
- `NUM_ENRS` (optional) – The number of ENRs to retrieve. 
Defaults to `3` if not specified.
- `SERVICE_NAME` (optional) – The Kubernetes service name
to query for pod IPs. Defaults to `zerotesting-bootstrap.zerotesting`.
- `OUTPUT_FILE` (optional) – Output file. Enables to retrieve multiple ENRS from different services 
(ie bootstrap, store,...). Defaults to `/etc/enr/ENR`.

### Example in Kubernetes yaml
```
initContainers:
  - name: grabenr
    image: <your-registry>/getenr:v1.1.0
    imagePullPolicy: IfNotPresent
    volumeMounts:
      - name: enr-data
        mountPath: /etc/enr
    command:
      - /app/getenr.sh
    args:
      - "3"
      - "status-service-bootstrap.status-go-test"
      - "/etc/enr/ENR"

...

command:
  - sh
  - -c
  - |
    . /etc/enr/ENR
    echo ENRs are $ENR1 $ENR2 $ENR3
    /usr/bin/wakunode --discv5-bootstrap-node=$ENR1
```

### Example in Kubernetes yaml using multiple services
```
initContainers:
  - name: grabenr
    image: <your-registry>/getenr:v1.1.0
    imagePullPolicy: IfNotPresent
    volumeMounts:
      - name: enr-data
        mountPath: /etc/enr
    command: ["/bin/sh", "-c"]
    args:
      - |
        /app/getenr.sh 3 status-service-bootstrap.status-go-test /etc/enr/BOOT_ENRS && \
        /app/getenr.sh 3 status-service-node.status-go-test /etc/enr/STORE_ENRS

...

command:
  - sh
  - -c
  - |
    set -a
    source /etc/enr/BOOT_ENRS
    source /etc/enr/STORE_ENRS
    set +a
    ...
```


### How It Works
1. **Fetch Pod IPs**: Uses nslookup to find the IPv4 addresses
of the specified service.
2. **Query Each Pod**: Sends an HTTP request 
to each pod at port `8645`, 
retrieving the enrUri from its debug API.
3. **Validate ENRs**: Ensures that the retrieved ENR
start with `enr:`, indicating a valid ENR format.
4. **Store Valid Addresses**: Saves valid ENRs
as environment variables in default file `/etc/enr/ENR`.

### Output
If successful, the script stores ENRs in default file `/etc/enr/ENR`
as environment variables:
```
export ENR1='enr:-MS4QGcHBZAnpu6qNYe_T6TGDCV6c9_3UsXlj5XlXY6QvLCUQKqajqDfs0aKOs7BISJzGxA7TuDzYXap4sP6JYUZ2Y9GAYh2F0dG5ldHOIAAAAAAAAAACEZXRoMpEJZZp0BAAAAf__________gmlkgnY0gmlwhC5QoeSJc2VjcDI1NmsxoQOZxJYJVoTfwo7zEom6U6L5Txrs3H9X0P_XBJbbOZBczYYN1ZHCCdl8'
```

### Changelog:

- 1.1.0
  - Added third variable to output result to given file.
  - Environmental variables  are renamed from `ENR1=...`, `ENR2=...` and so on to `<file_name>1=...`, `<file_name>2=...`
    - Default values remain unchanged
