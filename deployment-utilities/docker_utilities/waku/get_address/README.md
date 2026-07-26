## Waku Address Fetcher Script

This Bash script retrieves and validates the listening addresses 
of Waku nodes in a Kubernetes deployment. 
It queries a given service name to obtain pod IPs, 
then extracts and verifies the listenAddresses 
from each node's debug API. 
The valid addresses are saved in an environment file for further use.

It is intended to be used when we need to have multiaddress
to set up waku protocols like 
[store](https://docs.waku.org/guides/nwaku/config-options/#store-and-message-store-config), 
[filter](https://docs.waku.org/guides/nwaku/config-options/#filter-config) 
or 
[lightpush](https://docs.waku.org/guides/nwaku/config-options/#light-push-config).
In order to grab random multiaddress, we rely on kubernetes services.
For example, we assign every store node to a service for store nodes, 
and then we use this container to retrieve their multiaddresses.

### Usage:
```
./getaddress.sh [NUM_ADDRS] [SERVICE_NAME]
```

### Arguments:
- `NUM_ADDRS` (optional) – The number of addresses to retrieve. 
Defaults to `1` if not specified.
- `SERVICE_NAME` (optional) – The Kubernetes service name
to query for pod IPs. Defaults to `zerotesting-bootstrap.zerotesting`.

### Example in Kubernetes yaml
```
initContainers:
  - name: grabaddress
    image: <your-registry>/getaddress:v1.0.0
    imagePullPolicy: IfNotPresent
    volumeMounts:
      - name: address-data
        mountPath: /etc/addrs
    command:
      - /app/getaddress.sh
    args:
      - "1"
      - "zerotesting-lightpush-server.zerotesting"

...

command:
  - sh
  - -c
  - |
    . /etc/addrs/addrs.env
    echo addrs are $addrs1
    /usr/bin/wakunode --lightpushnode=$addrs1
```


### How It Works
1. **Fetch Pod IPs**: Uses nslookup to find the IPv4 addresses
of the specified service.
2. **Query Each Pod**: Sends an HTTP request 
to each pod at port `8645`, 
retrieving the listenAddresses from its debug API.
3. **Validate Addresses**: Ensures that the retrieved addresses
start with `/ip`, indicating a valid multiaddress format.
4. **Store Valid Addresses**: Saves valid addresses
as environment variables in `/etc/addrs/addrs.env`.

### Output
If successful, the script stores addresses in `/etc/addrs/addrs.env`
as environment variables:
```
export addrs1='/ip4/192.168.1.10/tcp/30303'
export addrs2='/ip4/192.168.1.11/tcp/30303'
```

