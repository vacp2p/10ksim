Scripts to test pushing a message from jswaku (lightpush client) on Kubernetes.

!!! You will have to manually perform this test !!!

# Tested on
jswaku version:
    commit: `dbdca49646c04d17eb99e1f4da6d3bda135cd928`
    branch: `feat/nwaku-style-lp-logs`
    image: 
nwaku:
    version: `v0.34.0-rc1`
    image: `soutullostatus/nwaku-jq-curl:v0.34.0-rc1`


# How to perform the test

The `grabaddress` initContainer does not select the listening address with `ws` (websocket), which is required for jswaku.
Therefore, you will have to look in the Lightpush Server (the nwaku pod) and get the listening address that has `ws`.
Then, go into the Lightpush Client (jswaku), using `kubectl exec -ti lpclient-0-0 sh` and do the following:
1. Export the Lightpush Server address to `addrs1` (note the 's' in "addrs1").
```
export addrs1='/ip4/10.1.4.15/tcp/8000/ws/p2p/16Uiu2HAm46LsAkC7XHXYe9Zfe7mskLzjA5iwgaojCHdcJAW3F6Ze'
```
2. Run jswaku with the appropriate parameters.
```
/usr/local/bin/docker-entrypoint.sh --cluster-id=2 --shard=0
```
3. Put the jswaku task in background (Ctrl+Z)
4. Use the jsawku API endpoint to push a message.
```
curl -X POST http://127.0.0.1:8080/lightpush/v3/message -H "Content-Type: application/json" -d '{ "pubsubTopic":"/waku/2/rs/2/0",   "message":     {"contentTopic": "/test/1/cross-network/proto", "payload" : "[1, 2, 3]"}}'
```
5. Bring the jswaku task back the the foreground and check the logs (Command: `fg 1`)
```
root@lpclient-0-0:/app# fg 1
/usr/local/bin/docker-entrypoint.sh --cluster-id=2 --shard=0
[Browser Console LOG] Pushing message via v3 lightpush: /test/1/cross-network/proto [1, 2, 3] /waku/2/rs/2/0
[Browser Console LOG] Waku node: WakuNode
[Browser Console LOG] Network config: {clusterId: 2}
[Browser Console LOG] Encoder: Encoder2
[Browser Console LOG] Pubsub topic: /waku/2/rs/2/0
[Browser Console LOG] Encoder pubsub topic: /waku/2/rs/2/0
[Browser Console LOG] ✅ Message sent via preferred lightpush node
[Browser Console LOG] Message hash: 34f4d3a1796855ccff9d07f0e7bb06c10c7a335c81b0ad0be5a4c713e2e87f6f
[pushMessageV3] Result: {
    "successes": [
        "16Uiu2HAm46LsAkC7XHXYe9Zfe7mskLzjA5iwgaojCHdcJAW3F6Ze"
    ],
    "failures": [],
    "myPeerId": "12D3KooWQ4kEq8Fg6NJ8ZTCVnqyPtrkzsfj5GFdbXMARcm6rYpXJ",
    "messageHash": "34f4d3a1796855ccff9d07f0e7bb06c10c7a335c81b0ad0be5a4c713e2e87f6f"
}
[Server] Message successfully sent via v3 lightpush!
```
