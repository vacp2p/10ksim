# Settings

# jswaku_commit_num=9d4eb2a6328d8b8d8609b0484c10ab4b190989c3
#jswaku_commit_num=6d92cb29ecc4201e20ae9b34016b31027f17793b
jswaku_commit_num=7a4158722f1a7308c64f72fcc8b643017a41cccc
jswaku_image="pearsonwhite/jswaku:${jswaku_commit_num}"

jswaku_internal_port=8080
jswaku_external_port=3000

nwaku_internal_port=8645
nwaku_external_port=8645

nwaku_image="pearsonwhite/nwaku_arm:v75375111acfc575"

node="localhost"

num_shards=1

custom_network_name="my_custom_network"

if ! docker network inspect "$custom_network_name" >/dev/null 2>&1; then
  docker network create --attachable --driver bridge "$custom_network_name"
fi


echo "--- Lightpush server ---"

nwaku_args=(--lightpush=true --relay=true --max-connections=500 --rest=true --rest-admin=true --rest-address=0.0.0.0 --discv5-discovery=true --discv5-enr-auto-update=True --log-level=INFO --metrics-server=True --metrics-server-address=0.0.0.0  --cluster-id=2 --websocket-support=true --num-shards-in-network=$num_shards --shard=0)
lps_container_id=$(docker run -d -ti --hostname="lpserver-0-0" --network="$custom_network_name" -p ${nwaku_external_port}:${nwaku_internal_port} ${nwaku_image} "${nwaku_args[@]}")
echo Lightpush Server Container Id: $lps_container_id
lps_container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID "'"$(docker network inspect -f '{{.Id}}' $custom_network_name)"'"}}{{.IPAddress}}{{end}}{{end}}' $lps_container_id)
echo Lightpush Server Ip: $lps_container_ip

echo "Wait for server"
sleep 5

addrs1=$(curl -X GET http://$node:${nwaku_external_port}/debug/v1/info \
  -H "Content-Type: application/json" | jq '.listenAddresses[1]' -r)
echo Lightpush Server address: $addrs1



echo "--- Relay node ---"

nwaku_relay_internal_port=8645
nwaku_relay_external_port=8648
nwaku_relay_args=(--relay=true --max-connections=500 --rest=true --rest-admin=true --rest-address=0.0.0.0 --discv5-discovery=true --discv5-enr-auto-update=True --log-level=INFO --metrics-server=True --metrics-server-address=0.0.0.0  --cluster-id=2 --websocket-support=true --staticnode=$addrs1 --num-shards-in-network=$num_shards --shard=0)
relay_container_id=$(docker run -d -ti --hostname="relay-node-0-0" --network="$custom_network_name" -p ${nwaku_relay_external_port}:${nwaku_relay_internal_port} ${nwaku_image} "${nwaku_relay_args[@]}")
echo Relay Server Container Id: $relay_container_id
relay_container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID "'"$(docker network inspect -f '{{.Id}}' $custom_network_name)"'"}}{{.IPAddress}}{{end}}{{end}}' $relay_container_id)
echo Relay Server Ip: $relay_container_ip

echo "Wait for server"
sleep 5


echo "--- Lightpush client (jswaku) ---"

jswaku_args=(--cluster-id=2 --shard=0)
lpc_container_id=$(docker run -d -ti --hostname="lpclient-0-0" --network="$custom_network_name" -p ${jswaku_external_port}:${jswaku_internal_port} --env "addrs1"=$addrs1 ${jswaku_image} "${jswaku_args[@]}")
echo Lightpush Client Container Id: $lpc_container_id
lpc_container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID "'"$(docker network inspect -f '{{.Id}}' $custom_network_name)"'"}}{{.IPAddress}}{{end}}{{end}}' $lpc_container_id)
echo Lightpush Client Ip: $lpc_container_ip


echo "Wait for client"
sleep 5

echo ""

curl -X GET http://$node:${jswaku_external_port}/waku/v1/peer-info \
  -H "Content-Type: application/json"

echo ""
echo ""

sleep 1

curl -X POST http://$node:${jswaku_external_port}/lightpush/v3/message \
  -H "Content-Type: application/json" \
  -d '{ "pubsubTopic":"/waku/2/rs/2/0",   "message": {"contentTopic": "/test/1/cross-network/proto", "payload" : "[1, 2, 3]"}}'

echo ""
echo ""

echo "done"
