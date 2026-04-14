NS=nomos-testnet
NAME=nomos
BASE=31000
REPLICAS=100   # pods nomos-0..nomos-99

OUT=nomos-nodeports.yaml
: > "$OUT"

for i in $(seq 0 $((REPLICAS-1))); do
  SWARM=$((BASE + 2*i))
  BLEND=$((BASE + 2*i + 1))

  cat >> "$OUT" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${NAME}-${i}-nodeport
  namespace: ${NS}
spec:
  type: NodePort
  selector:
    statefulset.kubernetes.io/pod-name: ${NAME}-${i}
  ports:
    - name: swarm
      protocol: UDP
      port: ${SWARM}
      targetPort: ${SWARM}
      nodePort: ${SWARM}
    - name: blend
      protocol: UDP
      port: ${BLEND}
      targetPort: ${BLEND}
      nodePort: ${BLEND}
---
EOF
done

echo "Wrote $OUT"
