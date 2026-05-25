kubectl cp -n test deployment-settings.yaml test-0:/data/volumes/nomos/test
kubectl cp -n test user_config_0.yaml test-0:/data/volumes/nomos/test
kubectl cp -n test user_config_1.yaml test-0:/data/volumes/nomos/test
kubectl cp -n test user_config_2.yaml test-0:/data/volumes/nomos/test
kubectl cp -n test user_config_3.yaml test-0:/data/volumes/nomos/test

# kubectl cp -n test deployment-settings.yaml test-1:/data/volumes/nomos/test
# kubectl cp -n test user_config_0.yaml test-1:/data/volumes/nomos/test
# kubectl cp -n test user_config_1.yaml test-1:/data/volumes/nomos/test
# kubectl cp -n test user_config_2.yaml test-1:/data/volumes/nomos/test
# kubectl cp -n test user_config_3.yaml test-1:/data/volumes/nomos/test