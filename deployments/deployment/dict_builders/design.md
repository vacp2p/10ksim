

# class types:

## Generic Builders
These are simple objects that provide a fluent interface for modifying configs.
The Builder pattern is just a very thin layer over the actual logic of incrementally building the config, which is done in helpers.
build() converts the config to a Kubernetes object.

## Waku Builders
These are built on top of the Generic Builders
These allow a convenient interface for changing various aspects of a specific deployment.
For example: .with_args() lets us "reach down" into the Waku container command so users don't need to know the internals. Because we expect to have this for Pod builds as well, the logic of "reaching down" is in a helper. But this still allows us to a convenient interface.

## Configs
Blueprints for building various Kubernetes objects.
(see Q/A for why we don't just use Kubernetes objects directly)

## Helpers / presets
### Presets
Groups logic for a single "feature" into one place. For example, if we want to know what a "store_node" feature entails, we can look at the StoreNode functions and see how configs are modified on each layer.

### Helpers
Useful for a variety of config manipulation.
Because this logic is reused a lot, it's in helpers to avoid duplicate logic in multiple Builders and Presets.

# Q/A

## Why use configs?
1. Kubernetes objects cannot be created without all required fields. Having a config allows us to incrementally create the deployements without needing to know all parameters ahead of time.
2. We can have our own objects that help use organize things better, such as the CommandConfig/Command classes that allow us to format commands in a much more readable form.
3. Some convenient helper functions, such as dealing with None => [] logic before appending sub-objects and automatic conversion logic for containers.
