### Waku

#### Message Tracking

In order to reconstruct the trace of a message, we need to check for every node X when this specific
node X received a message. Also, to represent X, we need to know this node id.

Currently, Waku logs when receives a message, together with the `timestamp`, `msg_hash` and `sender_peer_id`.
We also need to get the node X `peer_id` by checking at the beginning of the log this information.

With this information, we are able to create a dataframe with the following information:

|         **timestamp**         | **msg_hash** | sender_peer_id | receiver_peer_id |
|:-----------------------------:|:------------:|:--------------:|:----------------:|
| 2024-04-22 14:06:58.001+00:00 |     0x1      |       A        |        B         |
| 2024-04-22 14:06:58.002+00:00 |     0x1      |       B        |        D         |
| 2024-04-22 14:06:58.003+00:00 |     0x1      |       A        |        C         |
|              ...              |     ...      |      ...       |       ...        |

This information in form of a Dataframe has `timestamp` and `msg_hash` as indexes. This allow us to
fast and easily query information within time ranges, or just by a certain `msg_hash`. Then, with 
this in place, we can easily represent this information in the `visualizer` module.

- [ ] TODO: Add link to `visualizer` README.md when it is done.
