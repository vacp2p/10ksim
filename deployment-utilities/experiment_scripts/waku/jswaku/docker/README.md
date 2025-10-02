Local docker scripts to test pushing a message from jswaku (lightpush client).

Works with static sharding and autosharding.

# Tested on
jswaku version:
    commit: `7a4158722f1a7308c64f72fcc8b643017a41cccc`
    branch: `feat/simplify-browser-sim`
    image: `pearsonwhite/jswaku:7a4158722f1a7308c64f72fcc8b643017a41cccc`
nwaku:
    commit: `75375111acfc575ec57c10671780641d65fee241`
    branch: `release/v0.36`
    image: `pearsonwhite/nwaku_arm:v75375111acfc575`

# Test

1. Creates a local docker network
2. Runs lightpush server
3. Runs lightpush client
4. Pushes message from client to server

